import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.agent import answer_question
from app.probes import check_services, failure_codes
from app.settings import FrontendSettings

logger = logging.getLogger("uvicorn.error")


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def create_app(settings: FrontendSettings | None = None, answer_fn=None) -> FastAPI:
    settings = settings or FrontendSettings.from_env()
    answer_fn = answer_fn or answer_question
    ready = settings.local
    checks = {}
    error_codes = []
    recent = deque()
    total_requests = 0
    lock = asyncio.Lock()

    async def self_test():
        nonlocal ready, checks, error_codes
        for attempt in range(12):
            try:
                async with asyncio.timeout(90):
                    checks = await check_services(settings, checks)
                ready = True
                error_codes = []
                logger.info(json.dumps({"event": "startup_checks_passed", "checks": checks}))
                return
            except Exception as exc:
                error_codes = failure_codes(exc)
                logger.warning(
                    json.dumps(
                        {
                            "event": "startup_check_retry",
                            "attempt": attempt + 1,
                            "error_type": type(exc).__name__,
                            "error_codes": error_codes,
                            "checks": checks,
                        }
                    )
                )
                await asyncio.sleep(20)
        logger.error('{"event":"startup_checks_failed"}')

    @asynccontextmanager
    async def lifespan(app):
        task = None if settings.local else asyncio.create_task(self_test())
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def require_user(request: Request):
        # Easy Auth removes client-supplied identity headers on App Service.
        if not settings.local and (
            request.headers.get("x-ms-client-principal-id") != settings.operator_id
        ):
            raise HTTPException(403, "This user is not permitted")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "ready": ready,
            "version": settings.version,
            "checks": checks,
            "error_codes": error_codes,
        }

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        require_user(request)
        return HTMLResponse(
            Path(__file__).with_name("index.html").read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; "
                "style-src 'unsafe-inline'; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'",
            },
        )

    @app.post("/api/chat")
    async def chat(body: Question, request: Request):
        nonlocal total_requests
        require_user(request)
        if request.headers.get("origin") != settings.origin:
            raise HTTPException(403, "A same-origin request is required")
        if not ready:
            raise HTTPException(503, "The private services are not ready")
        if lock.locked():
            raise HTTPException(429, "Another request is running")
        now = time.monotonic()
        while recent and now - recent[0] >= 60:
            recent.popleft()
        if len(recent) >= 5 or total_requests >= 100:
            raise HTTPException(429, "Demo request limit reached")
        recent.append(now)
        total_requests += 1
        request_id = uuid.uuid4().hex
        async with lock:
            try:
                async with asyncio.timeout(90):
                    result = await answer_fn(settings, body.question)
            except Exception as exc:
                logger.error(
                    json.dumps(
                        {
                            "event": "chat_failed",
                            "request_id": request_id,
                            "error_type": type(exc).__name__,
                        }
                    )
                )
                raise HTTPException(502, f"処理に失敗しました。確認ID: {request_id}") from None
        logger.info(
            json.dumps(
                {
                    "event": "chat_complete",
                    "request_id": request_id,
                    "tools": result.tools,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "duration_ms": round((time.monotonic() - now) * 1000),
                }
            )
        )
        return {"answer": result.answer, "tools": result.tools, "request_id": request_id}

    return app
