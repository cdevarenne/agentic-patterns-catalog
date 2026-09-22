"""In-memory MCP tests. No network, no auth: the subject is `stdio-local`."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastmcp")
from fastmcp.client import Client
from fastmcp.exceptions import ToolError

from agentic_patterns_catalog import server, store
from agentic_patterns_catalog.model import (
    Content,
    Pattern,
    Provenance,
    Source,
    Tldr,
    content_hash,
)
from agentic_patterns_catalog.policy import AllowlistPDP


class ListLedger:
    def __init__(self) -> None:
        self.events: list[store.ActivityEvent] = []

    def append(self, event: store.ActivityEvent) -> None:
        self.events.append(event)


def _p(id: str, category: str = "routing", description: str | None = None) -> Pattern:
    # `tldr.what` (not `description`) feeds lexical search (see retrieval.pattern_text), so the
    # distinguishing text goes there. An identical placeholder in every record would starve BM25's
    # idf of any signal.
    text = description or f"{id} routes requests to handlers"
    c = Content(description=text, tldr=Tldr(what=text, when="n", watchOut="o"), code={"python": f"# {id}"})
    return Pattern(id=id, name=id.replace("-", " ").title(), category=category, complexity="low", content=c,
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


@pytest.fixture
def fs(tmp_path: Path) -> store.FileStore:
    s = store.FileStore(tmp_path, tmp_path / "cache")
    for p in (_p("content-router"), _p("semantic-router", description="semantic router picks a route by meaning"),
              _p("episodic-memory", "memory-management", "store and recall past episodes")):
        s.put(p)
    return s


@pytest.fixture
def ledger() -> ListLedger:
    return ListLedger()


@pytest.fixture
def mcp(fs: store.FileStore, ledger: ListLedger):
    return server.build_server(fs, AllowlistPDP(""), ledger)


def call(mcp, tool: str, **args: Any) -> Any:
    async def go():
        async with Client(mcp) as c:
            return (await c.call_tool(tool, args)).structured_content
    return asyncio.run(go())


def test_list_categories_counts_records(mcp) -> None:
    assert call(mcp, "list_categories")["result"] == [
        {"id": "memory-management", "patterns": 1}, {"id": "routing", "patterns": 2}]


def test_get_pattern_returns_the_record_with_content(mcp) -> None:
    rec = call(mcp, "get_pattern", id="content-router")
    assert rec["id"] == "content-router" and rec["content"]["code"] == {"python": "# content-router"}


def test_get_pattern_unknown_id_is_a_tool_error(mcp) -> None:
    with pytest.raises(ToolError, match="no pattern"):
        call(mcp, "get_pattern", id="nope")


def test_get_example_picks_language_or_says_none(mcp) -> None:
    assert call(mcp, "get_example", id="content-router", language="python")["code"] == "# content-router"
    assert call(mcp, "get_example", id="content-router", language="kotlin")["code"] is None


def test_search_patterns_is_lexical_and_filters_by_category(mcp) -> None:
    hits = call(mcp, "search_patterns", query="router")["result"]
    assert [h["id"] for h in hits][:2] == ["content-router", "semantic-router"] or \
        [h["id"] for h in hits][:2] == ["semantic-router", "content-router"]
    assert all(h["score_bm25"] > 0 for h in hits)
    assert call(mcp, "search_patterns", query="router", category="memory-management")["result"] == []


def test_select_returns_the_envelope_with_local_subject(mcp) -> None:
    env = call(mcp, "select", task="route a request by its meaning", k=2)
    assert env["auth"] == {"subject": "stdio-local"}
    assert env["retrieval_path"] == "bm25"  # no embedder in tests
    assert env["hits"][0]["id"] == "semantic-router"
    assert len(env["catalog_version"]) == 12


def test_select_rejects_an_unknown_facet(mcp) -> None:
    with pytest.raises(ToolError, match="unknown facet"):
        call(mcp, "select", task="x", facets={"colour": "red"})


def test_every_call_is_decided_and_written_before_the_body(mcp, ledger: ListLedger) -> None:
    call(mcp, "get_pattern", id="content-router")
    (e,) = ledger.events
    assert (e.tool, e.subject, e.decision, e.args, e.hits) == (
        "get_pattern", "stdio-local", "allow", {"id": "content-router"}, [])
    assert e.ts.endswith("Z") and e.provenance == {"role": "curator", "reason": "role 'curator' may call 'get_pattern'"}


def test_select_writes_a_result_row_with_hit_ids(mcp, ledger: ListLedger) -> None:
    env = call(mcp, "select", task="route by meaning", k=1)
    assert [e.decision for e in ledger.events] == ["allow", "result"]
    result = ledger.events[1]
    assert result.hits == [env["hits"][0]["id"]]
    assert result.provenance == {"catalog_version": env["catalog_version"], "retrieval_path": "bm25"}


def test_search_patterns_writes_a_result_row_with_hit_ids(mcp, ledger: ListLedger) -> None:
    hits = call(mcp, "search_patterns", query="router")["result"]
    assert [e.decision for e in ledger.events] == ["allow", "result"]
    result = ledger.events[1]
    assert result.hits == [h["id"] for h in hits]
    assert result.provenance == {}


def test_current_subject_is_none_over_http_with_no_token(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_http_request", lambda: object())
    monkeypatch.setattr(server, "get_access_token", lambda: None)
    assert server.current_subject() is None


def test_current_subject_is_local_over_stdio(monkeypatch) -> None:
    def _raise() -> None:
        raise RuntimeError("no active HTTP request")
    monkeypatch.setattr(server, "get_http_request", _raise)
    monkeypatch.setattr(server, "get_access_token", lambda: None)
    assert server.current_subject() == "stdio-local"


def test_denied_call_is_written_and_the_body_does_not_run(fs, ledger: ListLedger, monkeypatch) -> None:
    # The in-memory transport has no token, so the subject is stdio-local (a curator). Force a reader
    # to prove the deny path: patch current_subject.
    monkeypatch.setattr(server, "current_subject", lambda: "b@y.com")
    mcp = server.build_server(fs, AllowlistPDP("b@y.com:reader"), ledger)
    with pytest.raises(ToolError, match="may not call 'put_pattern'"):
        call(mcp, "put_pattern", record=fs.get("content-router").model_dump(mode="json"))
    (e,) = ledger.events
    assert (e.subject, e.decision, e.hits) == ("b@y.com", "deny", [])
    assert e.args["record"]["id"] == "content-router"


def test_unverified_subject_is_denied(fs, ledger: ListLedger, monkeypatch) -> None:
    monkeypatch.setattr(server, "current_subject", lambda: None)
    mcp = server.build_server(fs, AllowlistPDP("a@x.com:curator"), ledger)
    with pytest.raises(ToolError, match="no verified e-mail"):
        call(mcp, "list_categories")
    assert ledger.events[0].subject == "unknown" and ledger.events[0].decision == "deny"


def test_put_pattern_writes_through_the_store(mcp, fs, ledger: ListLedger) -> None:
    rec = fs.get("content-router").model_dump(mode="json")
    rec["content"]["description"] = "changed"
    assert call(mcp, "put_pattern", record=rec) == {"id": "content-router", "status": "written"}
    assert fs.get("content-router").content.description == "changed"


@pytest.mark.parametrize(("claims", "expected"), [
    ({"email": "a@x.com", "email_verified": True}, "a@x.com"),
    ({"email": "a@x.com", "email_verified": "true"}, "a@x.com"),
    ({"email": "a@x.com", "email_verified": False}, None),
    ({"email": "a@x.com"}, None),
    ({}, None),
])
def test_subject_from_claims(claims: dict[str, Any], expected: str | None) -> None:
    assert server.subject_from_claims(claims) == expected
