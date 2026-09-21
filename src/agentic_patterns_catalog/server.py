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
