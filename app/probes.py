import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from azure.identity.aio import ManagedIdentityCredential

from app.agent import answer_question
from app.settings import FrontendSettings


async def private_dns(url: str) -> bool:
    hostname = urlparse(url).hostname
    addresses = await asyncio.to_thread(socket.getaddrinfo, hostname, 443, type=socket.SOCK_STREAM)
    network = ipaddress.ip_network("10.42.0.0/16")
    return bool(addresses) and all(
        ipaddress.ip_address(item[4][0]) in network for item in addresses
    )


def failure_codes(error: BaseException) -> list[str]:
    """Keep useful diagnostics without returning exception messages or credentials."""
    pending = [error]
    seen = set()
    codes = set()
    while pending and len(seen) < 12:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        codes.add(type(current).__name__)
        codes.update(re.findall(r"\bAADSTS[0-9]{5,10}\b", str(current)))
        status = getattr(getattr(current, "response", None), "status_code", None)
        if isinstance(status, int) and 100 <= status <= 599:
            codes.add(f"HTTP_{status}")
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if current.__cause__:
            pending.append(current.__cause__)
    return sorted(codes)


async def check_services(
    settings: FrontendSettings,
    progress: dict[str, bool] | None = None,
) -> dict[str, bool]:
    """Run only at startup; anonymous health reads never trigger billable inference."""
    checks = progress if progress is not None else {}
    checks.clear()
    checks["mcp_private_dns"] = await private_dns(settings.mcp_url)
    checks["foundry_private_dns"] = await private_dns(settings.foundry_endpoint)
    async with httpx.AsyncClient(timeout=20) as http:
        response = await http.post(settings.mcp_url, json={})
        checks["mcp_rejects_anonymous"] = response.status_code == 401
        async with ManagedIdentityCredential(client_id=settings.identity_client_id) as credential:
            wrong_audience = await credential.get_token(
                "https://cognitiveservices.azure.com/.default"
            )
            response = await http.post(
                settings.mcp_url,
                json={},
                headers={"Authorization": f"Bearer {wrong_audience.token}"},
            )
        checks["mcp_rejects_wrong_audience"] = response.status_code == 401
    if not all(checks.values()):
        raise RuntimeError("Private connectivity or authentication probe failed")
    result = await answer_question(
        settings, "商品ID PC001 の在庫を確認し、数量を数字で答えてください。"
    )
    checks["foundry_mcp_tool_call"] = "get_inventory" in result.tools and "12" in result.answer
    if not all(checks.values()):
        raise RuntimeError("Foundry did not use the MCP inventory tool successfully")
    return checks
