"""Streamable HTTP with a bearer token: the e-mail claim becomes the subject the PDP decides on."""
from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator

import pytest

pytest.importorskip("fastmcp")
import uvicorn
from fastmcp.client import Client
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from tests.test_server import ListLedger, fs  # noqa: F401  (fixture re-export)

from agentic_patterns_catalog import server
from agentic_patterns_catalog.policy import AllowlistPDP

TOKENS = {
    "curator-token": {"client_id": "c", "scopes": ["openid"], "email": "a@x.com", "email_verified": True},
    "reader-token": {"client_id": "r", "scopes": ["openid"], "email": "b@y.com", "email_verified": True},
    "unverified-token": {"client_id": "u", "scopes": ["openid"], "email": "z@z.com", "email_verified": False},
}


@pytest.fixture
def http_server(fs) -> Iterator[tuple[str, ListLedger]]:  # noqa: F811
    ledger = ListLedger()
    mcp = server.build_server(fs, AllowlistPDP("a@x.com:curator,b@y.com:reader"), ledger,
                              auth=StaticTokenVerifier(tokens=TOKENS))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(mcp.http_app(path="/mcp"), host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    deadline = time.time() + 10
    while not srv.started and time.time() < deadline:
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}/mcp", ledger
    srv.should_exit = True
    th.join(5)


def _call(url: str, token: str | None, tool: str, **args):
    async def go():
        async with Client(url, auth=token) if token else Client(url) as c:
            return (await c.call_tool(tool, args)).structured_content
    return asyncio.run(go())


def test_bearer_email_is_the_subject(http_server) -> None:
    url, ledger = http_server
    env = _call(url, "reader-token", "select", task="route by meaning", k=1)
    assert env["auth"] == {"subject": "b@y.com"}
    assert ledger.events[0].subject == "b@y.com" and ledger.events[0].decision == "allow"


def test_reader_cannot_put_and_curator_can(http_server, fs) -> None:  # noqa: F811
    url, _ = http_server
    rec = fs.get("content-router").model_dump(mode="json")
    with pytest.raises(ToolError, match="may not call 'put_pattern'"):
        _call(url, "reader-token", "put_pattern", record=rec)
    assert _call(url, "curator-token", "put_pattern", record=rec)["status"] == "written"


def test_unverified_email_is_denied(http_server) -> None:
    url, ledger = http_server
    with pytest.raises(ToolError, match="no verified e-mail"):
        _call(url, "unverified-token", "list_categories")
    assert ledger.events[-1].subject == "unknown"


def test_no_token_is_rejected_before_any_tool_runs(http_server) -> None:
    url, ledger = http_server
    with pytest.raises(Exception):  # 401 from the auth layer: MCPError, never a ToolError  # noqa: B017
        _call(url, None, "list_categories")
    assert ledger.events == []
