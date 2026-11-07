from fastapi.testclient import TestClient

from app.agent import Answer
from app.frontend import create_app
from app.settings import FrontendSettings


def settings(local=True):
    return FrontendSettings(
        local,
        "http://localhost:8001/mcp",
        "http://localhost:9000",
        "demo",
        "https://demo.example",
        operator_id="owner",
    )


def test_health_does_not_call_model_and_chat_has_limits():
    calls = []

    async def answer(config, question):
        calls.append(question)
        return Answer("在庫12台", ["get_inventory"], 10, 5)

    with TestClient(create_app(settings(), answer)) as client:
        for _ in range(5):
            assert client.get("/health").status_code == 200
        assert calls == []
        assert client.post("/api/chat", json={"question": "在庫は？"}).status_code == 403
        assert (
            client.post(
                "/api/chat",
                json={"question": "在庫は？"},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        origin = {"Origin": "https://demo.example"}
        assert (
            client.post("/api/chat", json={"question": "x" * 2001}, headers=origin).status_code
            == 422
        )
        for _ in range(5):
            result = client.post("/api/chat", json={"question": "PC001の在庫は？"}, headers=origin)
            assert result.status_code == 200
            assert result.json()["tools"] == ["get_inventory"]
        assert (
            client.post("/api/chat", json={"question": "在庫は？"}, headers=origin).status_code
            == 429
        )


def test_frontend_rejects_missing_or_different_user():
    # Do not start Azure startup probes in this isolated authentication check.
    client = TestClient(create_app(settings(local=False)))
    assert client.get("/").status_code == 403
    assert client.get("/", headers={"X-MS-CLIENT-PRINCIPAL-ID": "other"}).status_code == 403
    response = client.get("/", headers={"X-MS-CLIENT-PRINCIPAL-ID": "owner"})
    assert response.status_code == 200
    assert "商品・在庫アシスタント" in response.text
