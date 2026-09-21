# Plan C — MCP Server, Google OAuth, Policy Layer, Postgres Store

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the catalog to agents over MCP (stdio for local use, Streamable HTTP with Google
login for remote use), with every tool call decided by a policy point and written to a ledger, and
with an optional Postgres mirror behind the existing `Store` and `Ledger` seams.

**Architecture:** One `FastMCP` server object built by `build_server(store, pdp, ledger, embedder)`.
A `PolicyMiddleware` resolves the caller's subject (`stdio-local`, or the verified Google e-mail),
asks the `PolicyDecisionPoint`, appends the decision to the `Ledger`, and only then lets the tool body
run. Two PDPs share one role table: `AllowlistPDP` (env string) and `OpaPDP` (HTTP to a local OPA that
evaluates `policy/catalog/authz.rego`); a parity test proves they agree. `PostgresStore` and
`PostgresLedger` implement the seams over `psycopg` + `pgvector`; `catalog sync-pg` loads them from the
files, which stay the source of truth.

**Tech Stack:** Python 3.14, uv, Pydantic v2, FastMCP 4 (extra `mcp`), `psycopg[binary]` 3 +
`pgvector` (extra `pg`), OPA 1.20.2 binary at `/opt/devel/opa` (dev only), PostgreSQL 18.6 + pgvector 0.8.6 (local).

**Spec:** `docs/superpowers/specs/2026-09-12-agentic-patterns-catalog-design.md` §4.6, §6, §6.1, §6.2,
§12, §14 steps 6–7. Issue: [#7](https://github.com/cdevarenne/agentic-patterns-catalog/issues/7).
Seams this plan consumes: `store.py` (`Store`, `Ledger`, `ActivityEvent`, `JsonlLedger`), `policy.py`
(`PolicyDecisionPoint`, `Decision`, `AllowlistPDP`, `TOOLS_BY_ROLE`, `LOCAL_SUBJECT`), `retrieval.py`
(`Selector`, `default_embedder`, `load_embedding_cache`).

## Facts verified on 2026-09-21 (the plan argues from these, not from memory)

- PyPI `fastmcp` is **4.0.5**. The spec says "v3"; the API this plan uses is identical in 4.0.5 and was
  probed in a scratch venv: `FastMCP(name, auth=...)`, `@mcp.tool`, `mcp.add_middleware(Middleware)`,
  `Middleware.on_call_tool(context, call_next)` with `context.message.name` / `.arguments`,
  `fastmcp.exceptions.ToolError` (propagates to the client as `ToolError`),
  `fastmcp.server.dependencies.get_access_token()`, `fastmcp.client.Client(mcp)` (in-memory),
  `Client("http://…/mcp", auth="<bearer>")`, `mcp.http_app(path="/mcp")` served by `uvicorn`
  (a FastMCP dependency).
- The in-memory transport carries no bearer token: `get_access_token()` returns `None` there and
  `Client(mcp, auth=...)` raises `ValueError("This transport does not support auth")`. HTTP-auth tests
  therefore start a real `uvicorn` server on a free port with
  `fastmcp.server.auth.providers.jwt.StaticTokenVerifier(tokens={"<token>": {"client_id": ..., "scopes": [...], "email": ...}})`;
  its `verify_token` returns `AccessToken(claims=token_data)`, so `claims["email"]` is what the test puts
  there. Without a token or with a bad one the server answers 401 and the client raises `MCPError`.
- `GoogleProvider(client_id, client_secret, base_url, redirect_path="/auth/callback" (default),
  required_scopes=[...])` (`fastmcp/server/auth/providers/google.py:253`). Its `GoogleTokenVerifier`
  fills `claims` with `sub, aud, email, email_verified, name, …` (`google.py:195-210`) and the OAuth
  proxy returns that validated token to `get_access_token()` (`oauth_proxy/proxy.py:2220`). So in HTTP
  mode the caller's e-mail is `get_access_token().claims["email"]`.
- Local PostgreSQL: `/opt/homebrew/opt/postgresql@18/bin/psql` (not on `PATH`), server 18.6 running as
  a brew service, `pg_available_extensions` shows `vector 0.8.6` installed. Only database `postgres`
  exists; peer auth as `cdev` works with DSN `postgresql:///postgres`.
- `psycopg[binary] 3.3.6` and `pgvector 0.5.0` install on Python 3.14 and round-trip a
  `numpy.float32` array through an untyped `vector` column with `pgvector.psycopg.register_vector`.
- OPA 1.20.2 (Rego v1) is installed by the owner at `/opt/devel/opa` (a single arm64 binary, not on `PATH`).

## Global Constraints

- Python `>=3.14`; uv; ruff line length 100; `uv run --extra lint ruff check .` and `uv run pytest`
  before every commit (CLAUDE.md).
- New dependencies that the deterministic path does not need go in an extra: `mcp`, `pg`. No `opa`
  Python extra: `OpaPDP` uses `urllib.request` from the standard library.
- Commits: one author (`cdevarenne`), one-line subject, no assistant attribution, straight to `main`,
  push after each task. No CI runs; the workflow stays `workflow_dispatch`.
- Every commit ships tests, or the commit message says why it cannot (docs-only).
- Secrets come from the environment only. `.env` is gitignored; `.env.example` names the variables.
  The server never reads `.env` itself; run it with `uv run --env-file .env catalog serve …`.
- Never widen trust silently: HTTP without auth configuration refuses to start; a token without a
  verified e-mail is denied; an unreachable OPA denies.
- Docs, docstrings, comments and commit messages in ASD-STE100 Simplified Technical English.
- Published numbers are generated, never typed.
- Tool names: `list_categories`, `search_patterns`, `get_pattern`, `get_example`, `select`,
  `put_pattern` (spec §6; they match the free pack's server).

## Rulings taken while writing this plan (each one is a spec amendment in Task 6)

| # | Ruling | Why | Cost if wrong |
|---|---|---|---|
| R1 | FastMCP **4** (`fastmcp>=4,<5`), not 3 | 4.0.5 is current; the surface used is identical; starting on a superseded major is debt | One version pin |
| R2 | Ledger writes **two rows** for an allowed `select`/`search_patterns`: the decision row before the body (`decision: allow`, `hits: []`) and a `decision: result` row after it with the hit ids and `{catalog_version, retrieval_path}`. Denied calls and the other tools write one row | The spec requires the decision to be written before the body runs; hit ids exist only after it. Append-only means a second row, not an update | `ActivityEvent.decision` gains the value `result`; SP7 reads two rows per query |
| R3 | `search_patterns` = BM25 arm of the shared `Selector` (`arm_scores`), filtered by category, top `k` (default 10). No gate, no semantic arm | It is a lexical search, the free pack's shape; `select` is the ranked, gated tool | A lexical-only search that never says "empty" |
| R4 | `list_categories` is derived from the records (`{id, patterns: n}`), not from `catalog/categories/` | Category records are gitignored site content and absent on a fresh clone | No category name in the answer |
| R5 | HTTP mode **requires** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`; `CATALOG_BASE_URL` defaults to `http://localhost:8000`. Missing → exit 2 | Secure by default: no anonymous HTTP | None |
| R6 | The subject is `claims["email"]` only when `claims["email_verified"]` is `True` or `"true"`; otherwise the call is denied with reason `token has no verified e-mail` | Google tokeninfo returns `email_verified` as a string | A Google account with an unverified e-mail cannot use the server |
| R7 | `PostgresStore` has five tables: the spec's `pattern`, `pattern_embedding`, `activity` plus `category(id, doc)` and `recipe(id, doc)` | The `Store` protocol has `categories()` and `recipes()` | Two small tables |
| R8 | `pattern.doc` holds the **merged** record (content included when cached). Postgres is a local mirror, never published | The server on `CATALOG_STORE=pg` must serve content | The mirror carries licensed text; `docs/auth.md` says so |
| R9 | `pattern_embedding.vec` is an untyped `vector` (no fixed dimension) keyed by `(id, model)` | The dimension follows the model (bge-small = 384); no index is needed for 288 rows | No ANN index (not needed) |
| R10 | Postgres tests run only when `CATALOG_PG_TEST_DSN` is set; each test uses its own schema and drops it | Keeps `uv run pytest` green on a bare machine and isolates tests | A skipped suite where Postgres is absent |
| R11 | `verify` gains a `pg` check that runs only when `CATALOG_PG_DSN` is set and `psycopg` imports; it compares row counts and `content_version` between files and Postgres. Skipped otherwise, and it says so | Spec: "`verify` runs its store checks against every configured store" | None |
| R12 | The OPA binary is found by `shutil.which("opa")`, else at `$OPA_BIN`; the parity test and `opa test policy/` skip when neither resolves | The owner keeps OPA at `/opt/devel/opa`, not on `PATH`; no brew install | A skipped test on machines without OPA |

## File structure

| Path | Responsibility |
|---|---|
| `src/agentic_patterns_catalog/server.py` | `build_server`, the six tools, `PolicyMiddleware`, `current_subject`, `serve` subcommand |
| `src/agentic_patterns_catalog/policy.py` | + `OpaPDP` (stdlib HTTP), `pdp_from_env` |
| `src/agentic_patterns_catalog/pgstore.py` | `PostgresStore`, `PostgresLedger`, `SCHEMA_SQL`, `sync-pg` subcommand |
| `src/agentic_patterns_catalog/store.py` | `ActivityEvent.decision` docstring (R2); no other change |
| `src/agentic_patterns_catalog/verify.py` | + `check_pg` (R11) |
| `src/agentic_patterns_catalog/commands.py` | + `pgstore`, `server` imports |
| `policy/catalog/authz.rego`, `policy/catalog/authz_test.rego` | The role table in Rego, and its tests |
| `tests/test_server.py`, `tests/test_server_http.py`, `tests/test_policy.py`, `tests/test_pgstore.py` | Tests |
| `docs/auth.md`, `.env.example`, `.mcp.json`, `README.md`, `CLAUDE.md`, spec, `.github/workflows/verify.yml` | Docs and wiring |

Environment variables (all read by `catalog serve` at start; none has a hidden default that widens trust):

| Variable | Values | Default |
|---|---|---|
| `CATALOG_ACCESS` | `a@x.com:curator,b@y.com:reader` | empty (only `stdio-local` may call) |
| `CATALOG_PDP` | `allowlist` \| `opa` | `allowlist` |
| `OPA_URL` | base URL | `http://localhost:8181` |
| `CATALOG_STORE` | `file` \| `pg` | `file` |
| `CATALOG_LEDGER` | `jsonl` \| `pg` | `jsonl` |
| `CATALOG_PG_DSN` | libpq DSN | none (required when store or ledger is `pg`) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | from the Cloud console | none (required by `--http`) |
| `CATALOG_BASE_URL` | public base URL | `http://localhost:8000` |

---

### Task 1: Server core — `build_server` and the five read tools over stdio

**Files:**
- Modify: `pyproject.toml` (extra `mcp = ["fastmcp>=4,<5"]`)
- Create: `src/agentic_patterns_catalog/server.py`
- Modify: `src/agentic_patterns_catalog/commands.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `FileStore`, `Store`, `Selector(patterns, embedder, arms)`, `Selector.select`,
  `Selector.arm_scores`, `Pattern`, `content_version`.
- Produces: `build_server(store: Store, pdp: PolicyDecisionPoint, ledger: Ledger, embedder: Embedder | None = None, auth: Any = None) -> FastMCP`;
  `ListLedger` test helper (in the test module). Task 2 adds the middleware into the same
  `build_server`; the `pdp` and `ledger` parameters exist from this task so the signature never changes.

- [ ] **Step 1: Add the extra and sync**

```toml
# pyproject.toml, [project.optional-dependencies]
# MCP server (stdio and Streamable HTTP). Optional so the CLI stays free of an HTTP stack.
mcp = ["fastmcp>=4,<5"]
```

Run: `uv sync --extra dev --extra mcp && uv run python -c "import fastmcp; print(fastmcp.__version__)"`
Expected: `4.0.x`

- [ ] **Step 2: Write the failing tests**

`tests/test_server.py`:

```python
"""In-memory MCP tests. No network, no auth: the subject is `stdio-local`."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastmcp")
from fastmcp.client import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from agentic_patterns_catalog import server, store  # noqa: E402
from agentic_patterns_catalog.model import Content, Pattern, Provenance, Source, Tldr, content_hash  # noqa: E402
from agentic_patterns_catalog.policy import AllowlistPDP  # noqa: E402


class ListLedger:
    def __init__(self) -> None:
        self.events: list[store.ActivityEvent] = []

    def append(self, event: store.ActivityEvent) -> None:
        self.events.append(event)


def _p(id: str, category: str = "routing", description: str | None = None) -> Pattern:
    c = Content(description=description or f"{id} routes requests to handlers",
                tldr=Tldr(what="w", when="n", watchOut="o"), code={"python": f"# {id}"})
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_server.py -q`
Expected: FAIL — `AttributeError: module 'agentic_patterns_catalog' has no attribute 'server'`.

- [ ] **Step 4: Write `server.py` (tools only; the middleware arrives in Task 2)**

```python
"""MCP server. One server object; stdio for local use, Streamable HTTP with Google login for remote use."""
from __future__ import annotations

from collections import Counter
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .model import Pattern
from .policy import PolicyDecisionPoint
from .retrieval import Embedder, Selector
from .store import Ledger, Store

SERVER_NAME = "agentic-patterns-catalog"


def build_server(store: Store, pdp: PolicyDecisionPoint, ledger: Ledger,
                 embedder: Embedder | None = None, auth: Any = None) -> FastMCP:
    """The server with its six tools. `auth` is a FastMCP auth provider; None means stdio (no auth)."""
    mcp = FastMCP(SERVER_NAME, auth=auth)
    selector = Selector.from_store(store, embedder)

    def _get(id: str) -> Pattern:
        try:
            return store.get(id)
        except KeyError:
            raise ToolError(f"no pattern with id {id!r}") from None

    @mcp.tool
    def list_categories() -> list[dict[str, Any]]:
        """Category ids with the number of patterns in each."""
        counts = Counter(p.category for p in store.all())
        return [{"id": c, "patterns": n} for c, n in sorted(counts.items())]

    @mcp.tool
    def get_pattern(id: str) -> dict[str, Any]:
        """The full record for `id`: identity, selection data, provenance and, when cached, the content."""
        return _get(id).model_dump(mode="json")

    @mcp.tool
    def get_example(id: str, language: str | None = None) -> dict[str, Any]:
        """The code example for `id` in `language` (default: the first one), or `code: null` when there is none."""
        p = _get(id)
        code = p.content.code if p.content else {}
        lang = language if language is not None else next(iter(code), None)
        return {"id": id, "language": lang, "code": code.get(lang) if lang else None,
                "languages": sorted(code)}

    @mcp.tool
    def search_patterns(query: str, category: str | None = None, k: int = 10) -> list[dict[str, Any]]:
        """Lexical (BM25) search. `category` limits the result to one category. Use `select` for a ranked pick."""
        bm25, _ = selector.arm_scores(query)
        by_id = {p.id: p for p in selector.patterns}
        ids = [i for i in sorted(bm25, key=lambda i: (-bm25[i], i)) if category in (None, by_id[i].category)]
        return [{"id": i, "name": by_id[i].name, "category": by_id[i].category, "score_bm25": bm25[i]}
                for i in ids[:k]]

    @mcp.tool
    def select(task: str, facets: dict[str, str] | None = None, k: int = 5) -> dict[str, Any]:
        """Pick the patterns that fit `task`. Facet names and values must come from the vocabulary."""
        try:
            return selector.select(task, facets or None, k).to_dict()
        except ValueError as e:
            raise ToolError(str(e)) from None

    @mcp.tool
    def put_pattern(record: dict[str, Any]) -> dict[str, str]:
        """Write one record (curators only). `content` present replaces the cached content."""
        try:
            pattern = Pattern.model_validate(record)
        except ValueError as e:
            raise ToolError(f"invalid record: {str(e).splitlines()[0]}") from None
        store.put(pattern)
        return {"id": pattern.id, "status": "written"}

    return mcp
```

Note for the implementer: FastMCP wraps a `list` return as `{"result": [...]}` in
`structured_content`; a `dict` return is passed through. The tests above assume that shape; if the
installed 4.x differs, adjust the tests' unwrapping, not the tool return types.

Add to `commands.py` (keep the alphabetical order; the import is guarded because `fastmcp` is an extra):

```python
import contextlib
with contextlib.suppress(ImportError):  # `mcp` extra absent: the `serve` subcommand is simply not registered
    from . import server  # noqa: F401
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_server.py -q`
Expected: 7 passed. Also `uv run pytest -q` (whole suite) and confirm `catalog --help` still works
without the extra: `uv run --no-sync --isolated python -c "..."` is overkill; instead check
`uv sync --extra dev && uv run catalog --help` lists no `serve` (Task 3 adds it) and imports cleanly,
then `uv sync --extra dev --extra mcp` again.

- [ ] **Step 6: Commit and push**

```bash
uv run --extra lint ruff check . && uv run pytest -q
git add pyproject.toml uv.lock src/agentic_patterns_catalog/server.py src/agentic_patterns_catalog/commands.py tests/test_server.py
git commit -m "Add the MCP server with the six catalog tools over stdio"
git push
```

---

### Task 2: Policy middleware, subject resolution, ledger rows, HTTP bearer test

**Files:**
- Modify: `src/agentic_patterns_catalog/server.py`
- Modify: `src/agentic_patterns_catalog/store.py:24-33` (`ActivityEvent` docstring: decision is `allow`, `deny` or `result`)
- Test: `tests/test_server.py` (append), `tests/test_server_http.py` (new)

**Interfaces:**
- Consumes: `PolicyDecisionPoint.decide(subject, tool, args) -> Decision`, `Ledger.append(ActivityEvent)`,
  `LOCAL_SUBJECT`, `get_access_token()`.
- Produces: `current_subject() -> str | None` (None = authenticated but no verified e-mail);
  `PolicyMiddleware(pdp, ledger)`; `RESULT_TOOLS = frozenset({"select", "search_patterns"})`;
  `utc_now() -> str` (ISO-8601 with `Z`). Task 4 and 5 reuse `ActivityEvent` as written here.

- [ ] **Step 1: Write the failing in-memory tests (append to `tests/test_server.py`)**

```python
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
```

`tests/test_server_http.py`:

```python
"""Streamable HTTP with a bearer token: the e-mail claim becomes the subject the PDP decides on."""
from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator

import pytest

pytest.importorskip("fastmcp")
import uvicorn  # noqa: E402
from fastmcp.client import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier  # noqa: E402

from agentic_patterns_catalog import server  # noqa: E402
from agentic_patterns_catalog.policy import AllowlistPDP  # noqa: E402
from tests.test_server import ListLedger, fs  # noqa: E402, F401  (fixture re-export)

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
        async with Client(url, auth=token) as c:
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_server.py tests/test_server_http.py -q`
Expected: FAIL — `AttributeError: … has no attribute 'current_subject'` / `subject_from_claims`; the
ledger tests fail with empty `events`.

- [ ] **Step 3: Implement the middleware and subject resolution in `server.py`**

Add after the imports:

```python
from datetime import UTC, datetime

from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from .policy import LOCAL_SUBJECT
from .store import ActivityEvent

RESULT_TOOLS = frozenset({"select", "search_patterns"})
UNKNOWN_SUBJECT = "unknown"


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def subject_from_claims(claims: dict[str, Any]) -> str | None:
    """The verified e-mail in a Google token's claims, or None. Google tokeninfo sends `email_verified` as text."""
    email = claims.get("email")
    return email if email and claims.get("email_verified") in (True, "true") else None


def current_subject() -> str | None:
    """`stdio-local` when no token is present (stdio), else the token's verified e-mail, else None."""
    token = get_access_token()
    if token is None:
        return LOCAL_SUBJECT
    return subject_from_claims(token.claims or {})


class PolicyMiddleware(Middleware):
    """Decide, write the decision to the ledger, then run the tool. A denied call never reaches the body."""

    def __init__(self, pdp: PolicyDecisionPoint, ledger: Ledger) -> None:
        self.pdp = pdp
        self.ledger = ledger

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        tool, args = context.message.name, dict(context.message.arguments or {})
        subject = current_subject()
        if subject is None:
            decision = Decision(False, "token has no verified e-mail", None)
            subject = UNKNOWN_SUBJECT
        else:
            decision = self.pdp.decide(subject, tool, args)
        self.ledger.append(ActivityEvent(
            ts=utc_now(), tool=tool, subject=subject, decision="allow" if decision.allow else "deny",
            args=args, hits=[], provenance={"role": decision.role, "reason": decision.reason}))
        if not decision.allow:
            raise ToolError(f"denied: {decision.reason}")
        result = await call_next(context)
        if tool in RESULT_TOOLS:
            self.ledger.append(ActivityEvent(
                ts=utc_now(), tool=tool, subject=subject, decision="result", args=args,
                hits=_hit_ids(tool, result.structured_content), provenance=_result_provenance(tool, result.structured_content)))
        return result


def _hit_ids(tool: str, structured: dict[str, Any] | None) -> list[str]:
    if not structured:
        return []
    rows = structured["hits"] if tool == "select" else structured.get("result", [])
    return [r["id"] for r in rows]


def _result_provenance(tool: str, structured: dict[str, Any] | None) -> dict[str, Any]:
    if tool != "select" or not structured:
        return {}
    return {"catalog_version": structured["catalog_version"], "retrieval_path": structured["retrieval_path"]}
```

Import `Decision` from `.policy`. In `build_server`, after `mcp = FastMCP(...)`:
`mcp.add_middleware(PolicyMiddleware(pdp, ledger))`. The `select` tool passes the subject into the
envelope: `selector.select(task, facets or None, k, subject=current_subject() or UNKNOWN_SUBJECT)`.

Store docstring (`store.py:26`): `"""One tool call as the ledger records it. `decision` is allow, deny or result; a denied call has no hits; a result row carries the hit ids."""`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_server.py tests/test_server_http.py -q`
Expected: all pass. If `result.structured_content` for a list-returning tool is not `{"result": [...]}`,
fix `_hit_ids` to match what Task 1 Step 5 observed — do not change the tool return type.

- [ ] **Step 5: Commit and push**

```bash
uv run --extra lint ruff check . && uv run pytest -q
git add src/agentic_patterns_catalog/server.py src/agentic_patterns_catalog/store.py tests/test_server.py tests/test_server_http.py
git commit -m "Decide and ledger every MCP tool call before its body runs"
git push
```

---

### Task 3: `catalog serve`, Google OAuth wiring, `docs/auth.md`, `.env.example`, `.mcp.json`

**Files:**
- Modify: `src/agentic_patterns_catalog/server.py` (the `serve` subcommand and `settings_from_env`)
- Create: `docs/auth.md`, `.env.example`, `.mcp.json`
- Modify: `README.md` (Commands table + a "MCP server" section)
- Test: `tests/test_server.py` (append)

**Interfaces:**
- Consumes: `register` from `cli.py`, `GoogleProvider`, `default_embedder`, `FileStore`, `JsonlLedger`, `AllowlistPDP`.
- Produces: `ServeSettings` dataclass and `settings_from_env(env: Mapping[str, str], http: bool) -> ServeSettings`
  (raises `ValueError` naming the missing variable); Task 4 extends it with `pdp`, Task 5 with `store`/`ledger`.

- [ ] **Step 1: Write the failing tests (append to `tests/test_server.py`)**

```python
def test_http_settings_require_google_client(monkeypatch) -> None:
    with pytest.raises(ValueError, match="GOOGLE_CLIENT_ID"):
        server.settings_from_env({}, http=True)
    s = server.settings_from_env({"GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "s"}, http=True)
    assert s.base_url == "http://localhost:8000" and s.http is True


def test_stdio_settings_need_nothing() -> None:
    s = server.settings_from_env({}, http=False)
    assert (s.http, s.google_client_id, s.access) == (False, None, "")


def test_serve_http_without_secrets_exits_2(capsys) -> None:
    from agentic_patterns_catalog.cli import main
    assert main(["serve", "--http"]) == 2
    assert "GOOGLE_CLIENT_ID" in capsys.readouterr().err
```

(The third test relies on the variables being unset in the test process; `monkeypatch.delenv(..., raising=False)` both names at the top of the test.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_server.py -q -k "settings or serve_http"`
Expected: FAIL — no `settings_from_env`; `serve` is not a command (argparse exit 2 but no stderr text, so the assertion on `err` fails).

- [ ] **Step 3: Implement settings and the subcommand (append to `server.py`)**

```python
import argparse
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass

from .cli import register
from .paths import CATALOG_DIR
from .policy import AllowlistPDP
from .retrieval import default_embedder
from .store import FileStore, JsonlLedger

DEFAULT_BASE_URL = "http://localhost:8000"
GOOGLE_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]


@dataclass(frozen=True)
class ServeSettings:
    http: bool
    access: str
    base_url: str
    google_client_id: str | None
    google_client_secret: str | None


def settings_from_env(env: Mapping[str, str], http: bool) -> ServeSettings:
    """Read the server's settings. HTTP needs the Google client; a missing variable is a ValueError that names it."""
    client_id, secret = env.get("GOOGLE_CLIENT_ID"), env.get("GOOGLE_CLIENT_SECRET")
    if http:
        for name, value in (("GOOGLE_CLIENT_ID", client_id), ("GOOGLE_CLIENT_SECRET", secret)):
            if not value:
                raise ValueError(f"--http needs {name} in the environment (see docs/auth.md)")
    return ServeSettings(http, env.get("CATALOG_ACCESS", ""), env.get("CATALOG_BASE_URL", DEFAULT_BASE_URL),
                         client_id, secret)


def google_auth(settings: ServeSettings) -> Any:
    from fastmcp.server.auth.providers.google import GoogleProvider

    return GoogleProvider(client_id=settings.google_client_id, client_secret=settings.google_client_secret,
                         base_url=settings.base_url, required_scopes=GOOGLE_SCOPES)


@register("serve", "run the MCP server (stdio by default; --http for Streamable HTTP with Google login)")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--http", action="store_true", help="Streamable HTTP on --host/--port; needs GOOGLE_CLIENT_*")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-embed", action="store_true", help="BM25 only")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)

    def run(ns: argparse.Namespace) -> int:
        try:
            settings = settings_from_env(os.environ, ns.http)
            pdp = AllowlistPDP(settings.access)
        except ValueError as e:
            print(f"serve: {e}", file=sys.stderr)
            return 2
        embedder = None if ns.no_embed else default_embedder()
        mcp = build_server(FileStore(ns.root), pdp, JsonlLedger(), embedder,
                           auth=google_auth(settings) if ns.http else None)
        if ns.http:
            mcp.run(transport="http", host=ns.host, port=ns.port, path="/mcp")
        else:
            mcp.run(transport="stdio")
        return 0
    return run
```

`.env.example`:

```sh
# Copy to .env (gitignored). Run: uv run --env-file .env catalog serve --http
GOOGLE_CLIENT_ID=            # Web application client, redirect http://localhost:8000/auth/callback
GOOGLE_CLIENT_SECRET=
CATALOG_BASE_URL=http://localhost:8000
CATALOG_ACCESS=you@example.com:curator
# CATALOG_PDP=allowlist       # or opa (needs `opa run --server -b policy/`)
# OPA_URL=http://localhost:8181
# CATALOG_STORE=file          # or pg
# CATALOG_LEDGER=jsonl        # or pg
# CATALOG_PG_DSN=postgresql:///agentic_patterns_catalog
```

`.mcp.json` (stdio, no auth; Claude Code picks it up from the repo root):

```json
{
  "mcpServers": {
    "agentic-patterns-catalog": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "catalog", "serve"]
    }
  }
}
```

`docs/auth.md` — sections, all in STE:

1. **What you need**: a Google Cloud project; an OAuth consent screen (External, Testing, your
   account as a test user); an OAuth client of type **Web application** with authorized redirect URI
   `http://localhost:8000/auth/callback`. State the assumption from spec §6.2: a Desktop-type client
   cannot be reused; the check is the client type shown in the console.
2. **Set the variables**: copy `.env.example` to `.env`; fill the two Google values and
   `CATALOG_ACCESS`. `.env` is gitignored.
3. **Run**: `uv sync --extra dev --extra mcp --extra embed` then
   `uv run --env-file .env catalog serve --http`. First call from an MCP client opens the browser;
   after consent the client holds a FastMCP-issued token; the server maps it to your e-mail.
4. **What the server checks** (the trust boundary, one line each): HTTP refuses to start without the
   client; a token without a verified e-mail is denied; the subject must be in `CATALOG_ACCESS`
   (`reader` or `curator`); every decision is written to `var/activity.jsonl` before the tool runs.
5. **Licence note**: `get_pattern` returns cached site content (© KORTEXYA, personal education).
   Only allowlist subjects who accept that licence.
6. **Manual login check** (the spec's "one manual login documented"): a checklist the owner ticks
   once the Web client exists — start, connect with `Client("http://localhost:8000/mcp", auth="oauth")`
   from a Python one-liner, call `select`, confirm `auth.subject` is the e-mail and one `allow` row
   landed in `var/activity.jsonl`. Leave the checkboxes unticked; the owner ticks them.

README: add `catalog serve [--http]` to the Commands table and a short "MCP server" section that
points to `docs/auth.md` and `.mcp.json`.

- [ ] **Step 4: Run the tests to verify they pass; smoke the stdio server by hand**

Run: `uv run pytest -q`
Then: `uv run --extra mcp python - <<'EOF'` with a `Client(PythonStdioTransport)`? Simpler:
`timeout 5 uv run catalog serve </dev/null; echo $?` should start and exit cleanly on EOF (exit 0 or
124 is acceptable; a traceback is not). Record the observed exit code in the commit body if it is 124.

- [ ] **Step 5: Commit and push**

```bash
uv run --extra lint ruff check . && uv run pytest -q
git add src/agentic_patterns_catalog/server.py tests/test_server.py docs/auth.md .env.example .mcp.json README.md
git commit -m "Add catalog serve with Google OAuth over Streamable HTTP"
git push
```

Then tell the owner: the HTTP path is built; the manual login in `docs/auth.md` §6 waits for the
Web-application OAuth client (redirect `http://localhost:8000/auth/callback`).

---

### Task 4: `OpaPDP`, the Rego policy, the parity test

**Files:**
- Modify: `src/agentic_patterns_catalog/policy.py`
- Create: `policy/catalog/authz.rego`, `policy/catalog/authz_test.rego`
- Modify: `src/agentic_patterns_catalog/server.py` (`CATALOG_PDP`, `OPA_URL` in `ServeSettings`)
- Modify: `.github/workflows/verify.yml` (an `opa test policy/` step)
- Modify: `CLAUDE.md` (local gate: `opa test policy/` when opa is installed)
- Test: `tests/test_policy.py` (append)

**Interfaces:**
- Consumes: `Decision`, `TOOLS_BY_ROLE`, `LOCAL_SUBJECT`, `parse_access`.
- Produces: `OpaPDP(url: str = "http://localhost:8181", access: str | None = None, timeout: float = 2.0)`;
  `OPA_DECISION_PATH = "/v1/data/catalog/authz/decision"`;
  `pdp_from_env(env: Mapping[str, str]) -> PolicyDecisionPoint`. The Rego reads the role map from
  `data.catalog.access` (`{subject: role}`) and answers `{"allow": bool, "reason": str, "role": str|null}`.

- [ ] **Step 0: Point the session at OPA (R12)**

Run: `export OPA_BIN=/opt/devel/opa && $OPA_BIN version | head -1`
Expected: `Version: 1.20.2`. Tests and the local gate use `opa_bin()` below; nothing is installed.

- [ ] **Step 1: Write the failing tests (append to `tests/test_policy.py`)**

```python
import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

POLICY_DIR = Path(__file__).resolve().parents[1] / "policy"


def _opa_stub(response: bytes | None, status: int = 200):
    """A one-route HTTP server that answers every POST with `response` (None = connection refused)."""
    seen: list[dict] = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(status); self.end_headers(); self.wfile.write(response or b"")
        def log_message(self, *a): pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}", seen


def test_opa_pdp_posts_the_input_and_reads_the_decision() -> None:
    srv, url, seen = _opa_stub(b'{"result": {"allow": true, "reason": "ok", "role": "reader"}}')
    try:
        d = policy.OpaPDP(url).decide("b@y.com", "select", {"task": "x"})
    finally:
        srv.shutdown()
    assert d == policy.Decision(True, "ok", "reader")
    assert seen == [{"input": {"subject": "b@y.com", "tool": "select", "args": {"task": "x"}}}]


def test_opa_pdp_denies_on_missing_result_and_on_unreachable_server() -> None:
    srv, url, _ = _opa_stub(b"{}")
    try:
        d = policy.OpaPDP(url).decide("b@y.com", "select", {})
    finally:
        srv.shutdown()
    assert d.allow is False and "no decision" in d.reason
    dead = policy.OpaPDP("http://127.0.0.1:9").decide("b@y.com", "select", {})
    assert dead.allow is False and "unreachable" in dead.reason


def test_pdp_from_env_picks_the_implementation() -> None:
    assert isinstance(policy.pdp_from_env({}), policy.AllowlistPDP)
    assert isinstance(policy.pdp_from_env({"CATALOG_PDP": "opa"}), policy.OpaPDP)
    with pytest.raises(ValueError, match="CATALOG_PDP"):
        policy.pdp_from_env({"CATALOG_PDP": "ldap"})


def opa_bin() -> str | None:
    """`opa` on PATH, else `$OPA_BIN` when it points at an executable, else None."""
    found = shutil.which("opa")
    if found:
        return found
    candidate = os.environ.get("OPA_BIN")
    return candidate if candidate and os.access(candidate, os.X_OK) else None


needs_opa = pytest.mark.skipif(opa_bin() is None, reason="opa not on PATH and OPA_BIN unset")


@needs_opa
def test_opa_unit_tests_pass() -> None:
    subprocess.run([opa_bin(), "test", str(POLICY_DIR)], check=True, capture_output=True)


@needs_opa
@pytest.mark.parametrize(
    ("subject", "tool"),
    [(s, t) for s in ("stdio-local", "a@x.com", "b@y.com", "nobody@x.com")
     for t in ("select", "get_pattern", "put_pattern", "drop_everything")],
)
def test_rego_agrees_with_the_allowlist(subject: str, tool: str, tmp_path: Path) -> None:
    access = "a@x.com:curator,b@y.com:reader"
    expected = policy.AllowlistPDP(access).decide(subject, tool, {})
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"catalog": {"access": policy.parse_access(access)}}))
    inp = tmp_path / "input.json"
    inp.write_text(json.dumps({"subject": subject, "tool": tool, "args": {}}))
    out = subprocess.run([opa_bin(), "eval", "-f", "json", "-d", str(POLICY_DIR), "-d", str(data), "-i", str(inp),
                          "data.catalog.authz.decision"], check=True, capture_output=True, text=True).stdout
    got = json.loads(out)["result"][0]["expressions"][0]["value"]
    assert (got["allow"], got["role"]) == (expected.allow, expected.role)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_policy.py -q`
Expected: FAIL — no `OpaPDP`, no `pdp_from_env`; `opa test` fails because `policy/` does not exist.

- [ ] **Step 3: Write the Rego**

`policy/catalog/authz.rego`:

```rego
# The same role table as policy.py TOOLS_BY_ROLE. tests/test_policy.py asserts the two agree.
package catalog.authz

import rego.v1

local_subject := "stdio-local"

read_tools := {"list_categories", "search_patterns", "get_pattern", "get_example", "select"}

tools_by_role := {
	"reader": read_tools,
	"curator": read_tools | {"put_pattern"},
}

role := "curator" if input.subject == local_subject

role := data.catalog.access[input.subject] if input.subject != local_subject

default decision := {"allow": false, "reason": "subject is not in the allowlist", "role": null}

decision := {"allow": true, "reason": sprintf("role %q may call %q", [role, input.tool]), "role": role} if {
	input.tool in tools_by_role[role]
}

decision := {"allow": false, "reason": sprintf("role %q may not call %q", [role, input.tool]), "role": role} if {
	role
	not input.tool in tools_by_role[role]
}
```

`policy/catalog/authz_test.rego`:

```rego
package catalog.authz_test

import data.catalog.authz
import rego.v1

access := {"a@x.com": "curator", "b@y.com": "reader"}

test_local_is_curator if {
	authz.decision.allow with input as {"subject": "stdio-local", "tool": "put_pattern", "args": {}}
}

test_reader_reads if {
	authz.decision.allow with input as {"subject": "b@y.com", "tool": "select", "args": {}}
		with data.catalog.access as access
}

test_reader_cannot_put if {
	d := authz.decision with input as {"subject": "b@y.com", "tool": "put_pattern", "args": {}}
		with data.catalog.access as access
	not d.allow
	d.role == "reader"
}

test_unknown_subject_denied if {
	d := authz.decision with input as {"subject": "x@x.com", "tool": "select", "args": {}}
		with data.catalog.access as access
	not d.allow
	d.role == null
}

test_unknown_tool_denied if {
	d := authz.decision with input as {"subject": "a@x.com", "tool": "drop_everything", "args": {}}
		with data.catalog.access as access
	not d.allow
}
```

Run `$OPA_BIN test policy/ -v` and `$OPA_BIN fmt --diff policy/` until both are clean. If the `import rego.v1`
form is rejected by OPA 1.x (it is the default there), delete the import lines.

- [ ] **Step 4: Implement `OpaPDP` and `pdp_from_env` (append to `policy.py`)**

```python
import json
import urllib.error
import urllib.request
from collections.abc import Mapping

OPA_DECISION_PATH = "/v1/data/catalog/authz/decision"
DEFAULT_OPA_URL = "http://localhost:8181"


class OpaPDP:
    """Asks a local OPA. Fails closed: no answer, a malformed answer or an unreachable server is a deny."""

    def __init__(self, url: str = DEFAULT_OPA_URL, timeout: float = 2.0) -> None:
        self.url = url.rstrip("/") + OPA_DECISION_PATH
        self.timeout = timeout

    def decide(self, subject: str, tool: str, args: dict[str, Any]) -> Decision:
        body = json.dumps({"input": {"subject": subject, "tool": tool, "args": args}}).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 — URL comes from config, not the caller
                result = json.loads(resp.read()).get("result")
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            return Decision(False, f"OPA unreachable: {e}", None)
        if not isinstance(result, dict) or "allow" not in result:
            return Decision(False, "OPA returned no decision", None)
        return Decision(bool(result["allow"]), str(result.get("reason", "")), result.get("role"))


def pdp_from_env(env: Mapping[str, str]) -> PolicyDecisionPoint:
    """`CATALOG_PDP=allowlist` (default) or `opa`. Any other value is a ValueError."""
    kind = env.get("CATALOG_PDP", "allowlist")
    if kind == "allowlist":
        return AllowlistPDP(env.get("CATALOG_ACCESS", ""))
    if kind == "opa":
        return OpaPDP(env.get("OPA_URL", DEFAULT_OPA_URL))
    raise ValueError(f"CATALOG_PDP={kind!r}; known: allowlist, opa")
```

In `server.py`'s `serve.run`, replace `pdp = AllowlistPDP(settings.access)` with
`pdp = pdp_from_env(os.environ)` (inside the same `try`). Note in `docs/auth.md` §"OPA": start OPA
with `opa run --server -b policy/ --set decision_logs.console=true` and load the access map with
`curl -X PUT localhost:8181/v1/data/catalog/access -d '{"you@example.com":"curator"}'`; the Rego
carries the role table, OPA data carries the subjects.

Workflow: add after the pytest step

```yaml
      - uses: open-policy-agent/setup-opa@v2
      - run: opa test policy/
```

CLAUDE.md, Conventions: `- Before every commit: ruff, pytest, and opa test policy/ (opa on PATH or $OPA_BIN).`

- [ ] **Step 5: Run the tests to verify they pass**

Run: `OPA_BIN=/opt/devel/opa uv run pytest tests/test_policy.py -q && $OPA_BIN test policy/ && $OPA_BIN fmt --diff policy/`
Expected: all pass (16 parity cases + 3 unit + 1 opa-test); `opa fmt` prints nothing.

- [ ] **Step 6: Commit and push**

```bash
uv run --extra lint ruff check . && uv run pytest -q
git add src/agentic_patterns_catalog/policy.py src/agentic_patterns_catalog/server.py policy/ tests/test_policy.py .github/workflows/verify.yml CLAUDE.md docs/auth.md
git commit -m "Add OpaPDP and the Rego role table; a parity test keeps both PDPs equal"
git push
```

---

### Task 5: `PostgresStore`, `PostgresLedger`, `catalog sync-pg`, `verify` pg check

**Files:**
- Modify: `pyproject.toml` (extra `pg = ["psycopg[binary]>=3.2", "pgvector>=0.4"]`)
- Create: `src/agentic_patterns_catalog/pgstore.py`
- Modify: `src/agentic_patterns_catalog/commands.py`, `src/agentic_patterns_catalog/verify.py`,
  `src/agentic_patterns_catalog/server.py` (`CATALOG_STORE`, `CATALOG_LEDGER`, `CATALOG_PG_DSN`)
- Modify: `tests/conftest.py` (the `pg_dsn` fixture), `README.md`, `docs/auth.md` (the "Postgres mirror" section)
- Test: `tests/test_pgstore.py`, `tests/test_verify.py` (append)

**Interfaces:**
- Consumes: `Store`, `Ledger`, `ActivityEvent`, `Pattern`, `Category`, `Recipe`, `dumps`,
  `content_version`, `load_embedding_cache`, `FileStore`.
- Produces: `PostgresStore(dsn: str, schema: str = "public")` with `.ensure_schema()`,
  `.sync_from(files: FileStore, embeddings_model: str | None = None) -> dict[str, int]`, and the
  `Store` methods; `PostgresLedger(dsn, schema="public")`; `SCHEMA_SQL`;
  `store_from_env(env, root) -> Store` and `ledger_from_env(env) -> Ledger` in `pgstore.py`
  (they return the file implementations when the env says so, so `server.py` imports them without the extra —
  the psycopg import lives inside the pg branch).

- [ ] **Step 0: Create the local database and pick the test DSN**

Run:
```bash
/opt/homebrew/opt/postgresql@18/bin/createdb agentic_patterns_catalog
/opt/homebrew/opt/postgresql@18/bin/psql -d agentic_patterns_catalog -c "create extension if not exists vector"
export CATALOG_PG_TEST_DSN=postgresql:///agentic_patterns_catalog
uv sync --extra dev --extra mcp --extra pg
```
The test DSN is exported for this session only; it is not written anywhere in the repo.

- [ ] **Step 1: Write the failing tests**

`tests/conftest.py` — append:

```python
import os
import uuid


@pytest.fixture
def pg_dsn() -> str:
    """The Postgres test DSN, or skip. Tests create their own schema and drop it (see `pg_schema`)."""
    dsn = os.environ.get("CATALOG_PG_TEST_DSN")
    if not dsn:
        pytest.skip("CATALOG_PG_TEST_DSN not set")
    return dsn


@pytest.fixture
def pg_schema(pg_dsn: str):
    psycopg = pytest.importorskip("psycopg")
    name = f"t_{uuid.uuid4().hex[:12]}"
    yield name
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(f'drop schema if exists "{name}" cascade')
```

`tests/test_pgstore.py`:

```python
"""PostgresStore and PostgresLedger against the local instance. Skipped without CATALOG_PG_TEST_DSN."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("psycopg")
from agentic_patterns_catalog import pgstore, retrieval, store  # noqa: E402
from agentic_patterns_catalog.model import Content, Pattern, Provenance, Source, Tldr, content_hash  # noqa: E402
from tests.test_server import _p  # noqa: E402


@pytest.fixture
def files(tmp_path: Path) -> store.FileStore:
    fs = store.FileStore(tmp_path, tmp_path / "cache", tmp_path / "emb")
    for p in (_p("content-router"), _p("semantic-router"), _p("episodic-memory", "memory-management")):
        fs.put(p)
    return fs


@pytest.fixture
def pg(pg_dsn: str, pg_schema: str) -> pgstore.PostgresStore:
    s = pgstore.PostgresStore(pg_dsn, schema=pg_schema)
    s.ensure_schema()
    return s


def test_sync_mirrors_the_files_and_the_version_agrees(pg: pgstore.PostgresStore, files: store.FileStore) -> None:
    counts = pg.sync_from(files)
    assert counts == {"patterns": 3, "categories": 0, "recipes": 0, "embeddings": 0, "removed": 0}
    assert [p.id for p in pg.all()] == ["content-router", "episodic-memory", "semantic-router"]
    assert pg.get("content-router").content.code == {"python": "# content-router"}
    assert store.content_version(pg.all()) == store.content_version(files.all())
    with pytest.raises(KeyError):
        pg.get("nope")


def test_sync_removes_rows_that_left_the_files(pg: pgstore.PostgresStore, files: store.FileStore, tmp_path: Path) -> None:
    pg.sync_from(files)
    (tmp_path / "patterns" / "routing" / "semantic-router.json").unlink()
    assert pg.sync_from(files)["removed"] == 1
    assert [p.id for p in pg.all()] == ["content-router", "episodic-memory"]


def test_put_writes_the_merged_record(pg: pgstore.PostgresStore, files: store.FileStore) -> None:
    pg.sync_from(files)
    changed = files.get("content-router")
    changed.content.description = "changed"
    changed.provenance.source.content_sha256 = content_hash(changed.content)
    pg.put(changed)
    assert pg.get("content-router").content.description == "changed"


def test_embeddings_round_trip_only_when_complete(pg: pgstore.PostgresStore, files: store.FileStore) -> None:
    emb = retrieval.HashEmbedder(dim=8)
    retrieval.build_embedding_cache(files.all(), emb, files.embeddings_dir)
    assert pg.sync_from(files, embeddings_model=emb.name)["embeddings"] == 3
    ids, matrix = pg.embeddings(emb.name)
    assert ids == ["content-router", "episodic-memory", "semantic-router"] and matrix.shape == (3, 8)
    assert np.allclose(matrix, retrieval.load_embedding_cache(files.all(), emb.name, files.embeddings_dir))
    assert pg.embeddings("other-model") is None


def test_ledger_appends_rows(pg_dsn: str, pg_schema: str, pg: pgstore.PostgresStore) -> None:
    ledger = pgstore.PostgresLedger(pg_dsn, schema=pg_schema)
    ledger.append(store.ActivityEvent("2026-09-21T00:00:00Z", "select", "a@x.com", "allow", {"task": "x"}, [], {}))
    ledger.append(store.ActivityEvent("2026-09-21T00:00:01Z", "select", "a@x.com", "result", {"task": "x"}, ["a", "b"],
                                      {"catalog_version": "abc"}))
    rows = ledger.tail(10)
    assert [(r["decision"], r["hits"]) for r in rows] == [("allow", []), ("result", ["a", "b"])]
    assert rows[1]["provenance"] == {"catalog_version": "abc"}


def test_store_and_ledger_from_env(pg_dsn: str, tmp_path: Path) -> None:
    assert isinstance(pgstore.store_from_env({}, tmp_path), store.FileStore)
    assert isinstance(pgstore.ledger_from_env({}), store.JsonlLedger)
    assert isinstance(pgstore.store_from_env({"CATALOG_STORE": "pg", "CATALOG_PG_DSN": pg_dsn}, tmp_path), pgstore.PostgresStore)
    with pytest.raises(ValueError, match="CATALOG_PG_DSN"):
        pgstore.store_from_env({"CATALOG_STORE": "pg"}, tmp_path)
    with pytest.raises(ValueError, match="CATALOG_LEDGER"):
        pgstore.ledger_from_env({"CATALOG_LEDGER": "redis"})
```

`tests/test_verify.py` — append:

```python
def test_pg_check_skips_without_dsn_and_reports_drift_with_one(monkeypatch, tmp_path, pg_dsn, pg_schema) -> None:
    from agentic_patterns_catalog import pgstore
    from tests.test_server import _p
    fs = store.FileStore(tmp_path, tmp_path / "cache")
    fs.put(_p("content-router"))
    ctx = verify.VerifyContext(tmp_path, False, tmp_path, tmp_path, tmp_path / "eval.json", tmp_path / "t.json", tmp_path / "cache")
    monkeypatch.delenv("CATALOG_PG_DSN", raising=False)
    assert verify.check_pg(ctx) == []
    monkeypatch.setenv("CATALOG_PG_DSN", pg_dsn)
    monkeypatch.setenv("CATALOG_PG_SCHEMA", pg_schema)
    pg = pgstore.PostgresStore(pg_dsn, schema=pg_schema)
    pg.ensure_schema()
    assert verify.check_pg(ctx) == ["postgres holds 0 patterns, files hold 1; run `catalog sync-pg`"]
    pg.sync_from(fs)
    assert verify.check_pg(ctx) == []
```

(`CATALOG_PG_SCHEMA` exists only so this test and `sync-pg --schema` can target a schema; default `public`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `CATALOG_PG_TEST_DSN=postgresql:///agentic_patterns_catalog uv run pytest tests/test_pgstore.py tests/test_verify.py -q`
Expected: FAIL — `ModuleNotFoundError: agentic_patterns_catalog.pgstore`; `verify` has no `check_pg`.
Also run once **without** the DSN and confirm the pg tests report `skipped`.

- [ ] **Step 3: Write `pgstore.py`**

```python
"""Postgres mirror of the files: `PostgresStore` and `PostgresLedger` (extra `pg`). Files stay the source of truth."""
from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .cli import register
from .model import Category, Pattern, Recipe
from .paths import CATALOG_DIR, CONTENT_CACHE_DIR, EMBEDDINGS_DIR
from .store import ActivityEvent, Embeddings, FileStore, JsonlLedger, Ledger, Store

SCHEMA_SQL = """
create extension if not exists vector;
create table if not exists {s}.pattern (
    id text primary key, doc jsonb not null, content_sha256 text not null, updated_at timestamptz not null default now());
create table if not exists {s}.category (id text primary key, doc jsonb not null);
create table if not exists {s}.recipe (id text primary key, doc jsonb not null);
create table if not exists {s}.pattern_embedding (
    id text not null references {s}.pattern(id) on delete cascade, model text not null, vec vector not null,
    primary key (id, model));
create table if not exists {s}.activity (
    id bigserial primary key, ts timestamptz not null, tool text not null, subject text not null,
    decision text not null, args jsonb not null, hits text[] not null, provenance jsonb not null);
"""


def _connect(dsn: str, schema: str):
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute(f'create schema if not exists "{schema}"')
    conn.execute(f'set search_path to "{schema}", public')
    conn.execute("create extension if not exists vector")
    register_vector(conn)
    return conn


class PostgresStore:
    """Records as jsonb in `pattern.doc` (content included when the files had it cached)."""

    def __init__(self, dsn: str, schema: str = "public") -> None:
        self.dsn, self.schema = dsn, schema

    def _conn(self):
        return _connect(self.dsn, self.schema)

    def ensure_schema(self) -> None:
        with self._conn() as c:
            c.execute(SCHEMA_SQL.format(s=f'"{self.schema}"'))

    def all(self) -> list[Pattern]:
        with self._conn() as c:
            rows = c.execute("select doc from pattern order by id").fetchall()
        return [Pattern.model_validate(r[0]) for r in rows]

    def get(self, id: str) -> Pattern:
        with self._conn() as c:
            row = c.execute("select doc from pattern where id = %s", (id,)).fetchone()
        if row is None:
            raise KeyError(id)
        return Pattern.model_validate(row[0])

    def put(self, pattern: Pattern) -> None:
        """Upsert the merged record. `content` None keeps the stored content (the doc is merged before the write)."""
        if pattern.content is None:
            try:
                pattern = pattern.model_copy(update={"content": self.get(pattern.id).content})
            except KeyError:
                pass
        doc = json.dumps(pattern.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        with self._conn() as c:
            c.execute("insert into pattern (id, doc, content_sha256) values (%s, %s::jsonb, %s) "
                      "on conflict (id) do update set doc = excluded.doc, content_sha256 = excluded.content_sha256, "
                      "updated_at = now()", (pattern.id, doc, pattern.provenance.source.content_sha256))

    def categories(self) -> list[Category]:
        with self._conn() as c:
            return [Category.model_validate(r[0]) for r in c.execute("select doc from category order by id")]

    def recipes(self) -> list[Recipe]:
        with self._conn() as c:
            return [Recipe.model_validate(r[0]) for r in c.execute("select doc from recipe order by id")]

    def embeddings(self, model_name: str) -> Embeddings | None:
        """Vectors for every pattern in id order, or None when any pattern lacks one for `model_name`."""
        with self._conn() as c:
            n = c.execute("select count(*) from pattern").fetchone()[0]
            rows = c.execute("select p.id, e.vec from pattern p join pattern_embedding e on e.id = p.id "
                             "where e.model = %s order by p.id", (model_name,)).fetchall()
        if not rows or len(rows) != n:
            return None
        return [r[0] for r in rows], np.stack([np.asarray(r[1], dtype=np.float32) for r in rows])

    def sync_from(self, files: FileStore, embeddings_model: str | None = None) -> dict[str, int]:
        """Make the tables equal to the files: upsert every record, delete the rest, copy the embedding cache."""
        from .retrieval import load_embedding_cache

        self.ensure_schema()
        patterns = files.all()
        ids = [p.id for p in patterns]
        for p in patterns:
            self.put(p)
        with self._conn() as c:
            removed = c.execute("delete from pattern where not (id = any(%s))", (ids,)).rowcount
            for table, docs in (("category", files.categories()), ("recipe", files.recipes())):
                c.execute(f"delete from {table}")
                for d in docs:
                    c.execute(f"insert into {table} (id, doc) values (%s, %s::jsonb)",
                              (d.id, json.dumps(d.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)))
            embedded = 0
            if embeddings_model:
                matrix = load_embedding_cache(patterns, embeddings_model, files.embeddings_dir)
                if matrix is not None:
                    c.execute("delete from pattern_embedding where model = %s", (embeddings_model,))
                    for id, vec in zip(sorted(ids), matrix, strict=True):
                        c.execute("insert into pattern_embedding (id, model, vec) values (%s, %s, %s)", (id, embeddings_model, vec))
                    embedded = len(ids)
        return {"patterns": len(ids), "categories": len(files.categories()), "recipes": len(files.recipes()),
                "embeddings": embedded, "removed": removed}


class PostgresLedger:
    """Append-only `activity` table; the shape of `ActivityEvent`, one row per event."""

    def __init__(self, dsn: str, schema: str = "public") -> None:
        self.dsn, self.schema = dsn, schema

    def append(self, event: ActivityEvent) -> None:
        with _connect(self.dsn, self.schema) as c:
            c.execute("insert into activity (ts, tool, subject, decision, args, hits, provenance) "
                      "values (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)",
                      (event.ts, event.tool, event.subject, event.decision, json.dumps(event.args),
                       event.hits, json.dumps(event.provenance)))

    def tail(self, n: int) -> list[dict[str, Any]]:
        """The last `n` rows, oldest first. For tests and for a look at the ledger."""
        with _connect(self.dsn, self.schema) as c:
            rows = c.execute("select ts, tool, subject, decision, args, hits, provenance from "
                             "(select * from activity order by id desc limit %s) t order by id", (n,)).fetchall()
        keys = ("ts", "tool", "subject", "decision", "args", "hits", "provenance")
        return [dict(zip(keys, r, strict=True)) for r in rows]


def _dsn(env: Mapping[str, str], what: str) -> str:
    dsn = env.get("CATALOG_PG_DSN")
    if not dsn:
        raise ValueError(f"{what}=pg needs CATALOG_PG_DSN")
    return dsn


def store_from_env(env: Mapping[str, str], root: Path = CATALOG_DIR) -> Store:
    """`CATALOG_STORE=file` (default) or `pg`."""
    kind = env.get("CATALOG_STORE", "file")
    if kind == "file":
        return FileStore(root, CONTENT_CACHE_DIR, EMBEDDINGS_DIR)
    if kind == "pg":
        return PostgresStore(_dsn(env, "CATALOG_STORE"), env.get("CATALOG_PG_SCHEMA", "public"))
    raise ValueError(f"CATALOG_STORE={kind!r}; known: file, pg")


def ledger_from_env(env: Mapping[str, str]) -> Ledger:
    """`CATALOG_LEDGER=jsonl` (default) or `pg`."""
    kind = env.get("CATALOG_LEDGER", "jsonl")
    if kind == "jsonl":
        return JsonlLedger()
    if kind == "pg":
        return PostgresLedger(_dsn(env, "CATALOG_LEDGER"), env.get("CATALOG_PG_SCHEMA", "public"))
    raise ValueError(f"CATALOG_LEDGER={kind!r}; known: jsonl, pg")


@register("sync-pg", "load the Postgres mirror from the files (extra pg)")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--dsn", default=os.environ.get("CATALOG_PG_DSN"), help="default: $CATALOG_PG_DSN")
    parser.add_argument("--schema", default=os.environ.get("CATALOG_PG_SCHEMA", "public"))
    parser.add_argument("--embeddings", metavar="MODEL", help="also copy the embedding cache for MODEL")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)

    def run(ns: argparse.Namespace) -> int:
        if not ns.dsn:
            print("sync-pg: set --dsn or CATALOG_PG_DSN", file=sys.stderr)
            return 2
        counts = PostgresStore(ns.dsn, ns.schema).sync_from(FileStore(ns.root), ns.embeddings)
        print(" ".join(f"{k}={v}" for k, v in counts.items()))
        return 0
    return run
```

(`import sys` at the top.) Note: `store_from_env` for `file` must pass the root's *matching* cache;
when `root` is not `CATALOG_DIR` (tests), the cache path is `root.parent / "var" / "content"` only in
the real tree — in tests, the file branch is asserted by type only.

`verify.py` — add `check_pg` after `check_eval` and register it as `("pg", check_pg)` at the end of `CHECKS`:

```python
def check_pg(ctx: VerifyContext) -> list[str]:
    """When `CATALOG_PG_DSN` is set and the pg extra is installed: the mirror holds the same records as the files."""
    dsn = os.environ.get("CATALOG_PG_DSN")
    if not dsn:
        return []
    try:
        from .pgstore import PostgresStore
        from .store import content_version
        pg = PostgresStore(dsn, os.environ.get("CATALOG_PG_SCHEMA", "public")).all()
    except ImportError:
        return ["CATALOG_PG_DSN is set but the pg extra is not installed"]
    files = FileStore(ctx.root, ctx.cache).all()
    if len(pg) != len(files):
        return [f"postgres holds {len(pg)} patterns, files hold {len(files)}; run `catalog sync-pg`"]
    if content_version(pg) != content_version(files):
        return ["postgres content differs from the files; run `catalog sync-pg`"]
    return []
```

`verify`'s printed line for a skipped pg check: in `run`, print `skip pg (CATALOG_PG_DSN unset)` instead
of `ok   pg` when the variable is unset — a plain `if name == "pg" and not os.environ.get("CATALOG_PG_DSN")`.

`server.py`: the `serve` handler builds `store_from_env(os.environ, ns.root)` and `ledger_from_env(os.environ)`
inside the same `try` as the settings (a `ValueError` prints and returns 2). `commands.py` imports `pgstore`
unconditionally (its psycopg imports are inside functions).

- [ ] **Step 4: Run the tests to verify they pass, then sync the real catalog once**

Run: `CATALOG_PG_TEST_DSN=postgresql:///agentic_patterns_catalog uv run pytest -q`
Then: `CATALOG_PG_DSN=postgresql:///agentic_patterns_catalog uv run catalog sync-pg --embeddings BAAI/bge-small-en-v1.5`
Expected: `patterns=288 categories=<n> recipes=2 embeddings=288 removed=0`
(`categories` is whatever `catalog/categories/` holds locally.) Then
`CATALOG_PG_DSN=postgresql:///agentic_patterns_catalog uv run catalog verify` → `ok   pg`, and
`uv run catalog verify` → `skip pg (CATALOG_PG_DSN unset)`. Record the two lines in the commit body.

- [ ] **Step 5: Docs**

README Commands table: `catalog sync-pg [--embeddings MODEL]` and `catalog serve`. New README section
"Postgres mirror (optional)": the extra, the DSN, `sync-pg`, that files stay the source of truth and
`verify` compares them. `docs/auth.md` gets a "Postgres mirror" paragraph: the mirror holds licensed
content; it is local; do not expose the database.

- [ ] **Step 6: Commit and push**

```bash
uv run --extra lint ruff check . && CATALOG_PG_TEST_DSN=postgresql:///agentic_patterns_catalog uv run pytest -q
git add pyproject.toml uv.lock src/agentic_patterns_catalog/pgstore.py src/agentic_patterns_catalog/commands.py src/agentic_patterns_catalog/verify.py src/agentic_patterns_catalog/server.py tests/conftest.py tests/test_pgstore.py tests/test_verify.py README.md docs/auth.md
git commit -m "Add the Postgres mirror: PostgresStore, PostgresLedger, sync-pg and a verify check"
git push
```

---

### Task 6: Spec amendments, ADR-0005, architecture diagram, close-out

**Files:**
- Modify: `docs/superpowers/specs/2026-09-12-agentic-patterns-catalog-design.md` §4.6, §6, §6.1, §14
- Create: `docs/adr/0005-mcp-server-and-policy-layer.md`
- Modify: `docs/architecture.mmd`, `CLAUDE.md`, `README.md` (if a line is still missing)

Docs only; this commit ships no tests and the message says so.

- [ ] **Step 1: Amend the spec** — one line each, marked `(amended 2026-09-21, Plan C)`:
  §6 table: FastMCP **4** (R1); the `ActivityEvent` `result` row (R2); `search_patterns` semantics (R3);
  `list_categories` derived from records (R4); HTTP refuses to start without the Google client (R5);
  verified e-mail rule (R6). §4.6: the five tables (R7), merged doc (R8), untyped vector keyed by
  `(id, model)` (R9), `verify` pg check (R11), `sync-pg` flags. §6.1: no Python `opa` extra;
  `OPA_URL`; role map lives in OPA data `catalog.access`, the role table in Rego. §14 steps 6–7:
  "done in Plan C (commits …)".

- [ ] **Step 2: Write ADR-0005** — Context (the seams from #1 and the spec); Decision (server shape:
  one object, two transports, middleware-first policy, two-row ledger, fail-closed PDPs, Postgres as a
  mirror); Consequences (bare install unchanged; three extras; the manual login step waits on the Cloud
  console; SP7 reads `result` rows); Rulings table R1–R12 copied from this plan with their costs.
  Status: implemented in Plan C.

- [ ] **Step 3: Update `docs/architecture.mmd`** — add the `server.py` node (stdio / HTTP+Google),
  `PolicyMiddleware → PDP {Allowlist, OPA}`, `Ledger {jsonl, pg}`, `Store {file, pg}`, `sync-pg` edge
  from files to Postgres. Check it renders: `npx -y @mermaid-js/mermaid-cli -i docs/architecture.mmd -o /tmp/a.svg`
  is optional; at minimum `grep -c '\-\->' docs/architecture.mmd` grows and the file parses in the
  GitHub preview after push.

- [ ] **Step 4: CLAUDE.md** — Toolchain line: extras `mcp`, `pg`, `embed`; the local gate line from
  Task 4; one line: "`catalog serve` reads its settings from the environment; never load `.env` in code."

- [ ] **Step 5: Commit, push, close the issue**

```bash
uv run --extra lint ruff check . && uv run pytest -q && uv run catalog verify
git add docs/ CLAUDE.md README.md
git commit -m "Record Plan C in the spec, ADR-0005 and the architecture diagram" -m "Docs only; no tests."
git push
gh issue comment 7 --body "$(cat <<'EOF'
Landed on main: <commit list>. FastMCP 4 (spec said 3; API identical, R1 in ADR-0005). Rulings R1–R12 in docs/adr/0005-mcp-server-and-policy-layer.md.
Open follow-ups: the manual Google login (docs/auth.md §6) needs the Web-application OAuth client; the CI step `opa test policy/` is committed but inert (#6).
EOF
)"
gh issue close 7
```

## Self-review

**Spec coverage.** §6 tools and transports → Tasks 1–3. §6 `GoogleProvider` values from env → Task 3.
§6.1 `AllowlistPDP` default, `OpaPDP`, `policy/catalog/authz.rego`, `opa test policy/`, parity test,
"every decision appended before the tool body" → Tasks 2 and 4. §6.2 `docs/auth.md`, `.env`,
`.env.example` → Task 3. §4.6 `PostgresStore`/`PostgresLedger`, extra `pg`, `sync-pg`, mirror semantics,
`verify` against every configured store → Task 5. §14 step 6 checks (PDP parity test; denied/allowed
with a fake token verifier; one manual login documented) → Tasks 2, 4, 3. §14 step 7 → Task 5.
Issue #7 scope lines are all covered. Not in scope and said so: `langgraph-checkpoint-postgres`
(Plan D's Python agent), SP3 policies beyond RBAC.

**Placeholder scan.** No TBD/TODO. Every code step shows the code. Task 6 is docs with named sections
and a stated "no tests" reason.

**Type consistency.** `build_server(store, pdp, ledger, embedder=None, auth=None)` in Tasks 1, 2, 3,
5. `ActivityEvent(ts, tool, subject, decision, args, hits, provenance)` positional order matches
`store.py`. `Decision(allow, reason, role)` positional in Tasks 2 and 4. `PostgresStore(dsn, schema)`,
`.ensure_schema()`, `.sync_from(files, embeddings_model)`, `.embeddings(model_name) -> (ids, matrix)`
consistent between Task 5 tests and code. `settings_from_env(env, http)` in Task 3; Task 4 swaps only
the PDP construction; Task 5 swaps store and ledger construction. `_p` helper is defined in
`tests/test_server.py` and imported by Tasks 2 and 5 tests; `fs` fixture re-exported to
`test_server_http.py` by import (pytest accepts a fixture imported into the module namespace).

**Known risks the executor should watch.** (a) `structured_content` shape for list-returning tools
(`{"result": [...]}`) — verified for 4.0.5 by the docs snippet, not by a run in this checkout; Task 1
Step 5 confirms. (b) `Client(url, auth=None)` on the HTTP test: pass no `auth` kwarg when the token is
None. (c) `opa eval` output path `result[0].expressions[0].value` — standard, confirm on the first run.
(d) `pgvector` returns a `Vector` object; `np.asarray(row, dtype=float32)` converts it (verified).
