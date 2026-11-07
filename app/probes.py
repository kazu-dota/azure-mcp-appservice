import asyncio
import ipaddress
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


async def check_services(settings: FrontendSettings) -> dict[str, bool]:
    """Run only at startup; anonymous health reads never trigger billable inference."""
    checks = {
        "mcp_private_dns": await private_dns(settings.mcp_url),
        "foundry_private_dns": await private_dns(settings.foundry_endpoint),
    }
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
