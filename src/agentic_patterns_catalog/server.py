"""MCP server. One server object; stdio for local use, Streamable HTTP with Google login for remote use."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from .model import Pattern
from .policy import LOCAL_SUBJECT, Decision, PolicyDecisionPoint
from .retrieval import Embedder, Selector
from .store import ActivityEvent, Ledger, Store

SERVER_NAME = "agentic-patterns-catalog"
RESULT_TOOLS = frozenset({"select", "search_patterns"})
UNKNOWN_SUBJECT = "unknown"


def utc_now() -> str:
    """The current time, ISO-8601, second precision, with a `Z` suffix."""
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
                hits=_hit_ids(tool, result.structured_content),
                provenance=_result_provenance(tool, result.structured_content)))
        return result


def _hit_ids(tool: str, structured: dict[str, Any] | None) -> list[str]:
    """The pattern ids a `select` or `search_patterns` call returned, for the ledger row."""
    if not structured:
        return []
    rows = structured["hits"] if tool == "select" else structured.get("result", [])
    return [r["id"] for r in rows]


def _result_provenance(tool: str, structured: dict[str, Any] | None) -> dict[str, Any]:
    """The `select` envelope's catalog version and retrieval path, for the ledger row. Empty for `search_patterns`."""
    if tool != "select" or not structured:
        return {}
    return {"catalog_version": structured["catalog_version"], "retrieval_path": structured["retrieval_path"]}


def build_server(store: Store, pdp: PolicyDecisionPoint, ledger: Ledger,
                 embedder: Embedder | None = None, auth: Any = None) -> FastMCP:
    """The server with its six tools. `auth` is a FastMCP auth provider; None means stdio (no auth)."""
    mcp = FastMCP(SERVER_NAME, auth=auth)
    mcp.add_middleware(PolicyMiddleware(pdp, ledger))
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
            return selector.select(task, facets or None, k,
                                   subject=current_subject() or UNKNOWN_SUBJECT).to_dict()
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
