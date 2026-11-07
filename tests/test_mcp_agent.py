import os
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest
from mcp import Client

from app.agent import run_agent


@pytest.fixture(scope="module")
def mcp_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, APP_ENV="local")
    env.pop("WEBSITE_SITE_NAME", None)
    env.pop("WEBSITE_HOSTNAME", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.mcp_server:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                with urlopen(base + "/health", timeout=0.5) as response:
                    assert response.status == 200
                break
            except OSError:
                if process.poll() is not None:
                    pytest.fail("MCP test server exited")
                time.sleep(0.1)
        else:
            pytest.fail("MCP test server did not start")
        yield base + "/mcp"
    finally:
        process.terminate()
        process.wait(timeout=10)


async def test_real_http_transport_and_inventory(mcp_url):
    async with Client(mcp_url) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools.tools} == {"search_products", "get_inventory"}
        result = await client.call_tool("get_inventory", {"product_id": "PC001"})
        assert result.structured_content["stock"] == 12
        missing = await client.call_tool("get_inventory", {"product_id": "ZZ999"})
        assert missing.structured_content["found"] is False
        invalid = await client.call_tool("get_inventory", {"product_id": "../../secret"})
        assert invalid.is_error


async def test_tool_loop_uses_actual_mcp_result(mcp_url):
    responses = iter(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {
                            "name": "get_inventory",
                            "arguments": '{"product_id":"PC001"}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "軽量ノートPCの在庫は12台です。"},
        ]
    )

    async def complete(messages, tools):
        assert len(tools) == 2
        if messages[-1]["role"] == "tool":
            assert '"stock":12' in messages[-1]["content"]
        return {
            "choices": [{"message": next(responses)}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    async with Client(mcp_url) as client:
        answer = await run_agent(client, complete, "PC001の在庫は？")
    assert answer.tools == ["get_inventory"]
    assert "12" in answer.answer
    assert (answer.input_tokens, answer.output_tokens) == (20, 10)


async def test_unknown_tool_and_excessive_calls_fail_closed(mcp_url):
    async def complete(messages, tools):
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "bad",
                                "type": "function",
                                "function": {"name": "delete_everything", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ]
        }

    async with Client(mcp_url) as client:
        with pytest.raises(ValueError, match="unknown tool"):
            await run_agent(client, complete, "不正な操作")

    async def repeated(messages, tools):
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": str(i),
                                "type": "function",
                                "function": {
                                    "name": "get_inventory",
                                    "arguments": '{"product_id":"PC001"}',
                                },
                            }
                            for i in range(5)
                        ]
                    }
                }
            ]
        }

    async with Client(mcp_url) as client:
        with pytest.raises(ValueError, match="budget"):
            await run_agent(client, repeated, "回数超過")
