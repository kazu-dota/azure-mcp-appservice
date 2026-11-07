FROM ghcr.io/astral-sh/uv:0.9.26 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
RUN useradd --uid 10001 --create-home app
USER 10001
EXPOSE 8000
ENV APP_MODULE=app.frontend:create_app
CMD ["sh", "-c", "exec .venv/bin/uvicorn \"$APP_MODULE\" --factory --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
