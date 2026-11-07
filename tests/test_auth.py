import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import TokenVerifier
from app.mcp_server import create_app
from app.settings import McpSettings, local_mode


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def secured(signing_key):
    settings = McpSettings(False, "testserver", "tenant", "mcp-api", "frontend", "frontend-oid")
    keys = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=signing_key.public_key())
    )
    verifier = TokenVerifier(settings, keys)
    with TestClient(create_app(settings, verifier)) as client:
        yield client


def make_token(key, **overrides):
    claims = {
        "iss": "https://login.microsoftonline.com/tenant/v2.0",
        "aud": "mcp-api",
        "tid": "tenant",
        "oid": "frontend-oid",
        "azp": "frontend",
        "roles": ["Mcp.Invoke"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"aud": "https://cognitiveservices.azure.com"}, 401),
        ({"iss": "https://login.microsoftonline.com/other/v2.0"}, 401),
        ({"exp": int(time.time()) - 300}, 401),
        ({"oid": "another-app"}, 403),
        ({"azp": "another-app"}, 403),
        ({"roles": []}, 403),
        ({"roles": "Mcp.InvokeExtra"}, 403),
    ],
)
def test_wrong_tokens_are_rejected(secured, signing_key, overrides, expected):
    response = secured.post(
        "/mcp", json={}, headers={"Authorization": "Bearer " + make_token(signing_key, **overrides)}
    )
    assert response.status_code == expected


def test_missing_and_invalid_signature_are_rejected(secured):
    assert secured.post("/mcp", json={}).status_code == 401
    another_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert (
        secured.post(
            "/mcp", json={}, headers={"Authorization": "Bearer " + make_token(another_key)}
        ).status_code
        == 401
    )


def test_expected_identity_reaches_mcp(secured, signing_key):
    response = secured.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={
            "Authorization": "Bearer " + make_token(signing_key),
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        },
    )
    assert response.status_code == 200
    assert {tool["name"] for tool in response.json()["result"]["tools"]} == {
        "search_products",
        "get_inventory",
    }


def test_local_bypass_is_forbidden_on_azure(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("WEBSITE_SITE_NAME", "production-site")
    with pytest.raises(RuntimeError, match="forbidden"):
        local_mode()
