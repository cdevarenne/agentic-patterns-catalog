# Tool Retrieval (Tool RAG)

Category: tool-use | Complexity: medium

When an agent can reach hundreds or thousands of tools or MCP servers, loading every schema into the prompt is expensive and hurts selection accuracy. Tool retrieval indexes tool definitions and, for each query, retrieves only the semantically relevant ones (embedding search, active discovery, and reranking) before the model chooses. RAG-MCP reports tool-selection accuracy rising from about 13 percent to 43 percent while cutting prompt tokens by more than half.

## In 30 seconds

- **What:** Indexes tool definitions by embedding, retrieves only semantically relevant schemas per query, then reranks before the model selects.
- **When:** Agents access hundreds or thousands of tools and loading all schemas wastes tokens and degrades selection accuracy.
- **Watch out:** Retrieval failures (poor embedding match or ranking) silently omit the correct tool, causing the agent to pick a suboptimal alternative.

## Key features

- Vector index over tool and MCP server definitions
- Per-query semantic retrieval of relevant tools only
- Reranking to shortlist the top-k candidate tools
- Active, on-demand discovery instead of preloading all schemas
- Large prompt-token reduction versus loading every schema
- Higher tool-selection accuracy at scale (thousands of tools)

## Use cases

- large-tool-catalogs
- mcp-ecosystems
- token-optimization
- tool-selection
- scalable-agents

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Setup: the agent is connected to 4000 MCP tools; loading all schemas would be roughly 600K tokens.

Query: "Convert this invoice PDF to CSV and email it to finance"

1. Embed the query and search the tool index
2. Retrieve and rerank -> top 5 tools (pdf_extract, table_to_csv, email_send, ...)
3. Load only those 5 schemas (~2K tokens) into the prompt
4. Model selects pdf_extract -> table_to_csv -> email_send and calls them

Result: correct tools called with ~2K tool tokens instead of ~600K, and selection accuracy improves because the model is not distracted by thousands of irrelevant schemas
```

## Implementation (python)

```python
#!/usr/bin/env python3
# Tool Retrieval (Tool RAG): with a large tool catalog, loading every schema is
# costly and confuses selection. Here a keyword-overlap scorer stands in for an
# embedding retriever: it scores each tool against the query, reranks, keeps the
# top-k, and only those schemas enter the prompt. The model then selects a
# pipeline from that shortlist. The demo prints scores and the token savings.

import re
from dataclasses import dataclass
from typing import List

TOP_K = 5

@dataclass
class Tool:
    name: str
    description: str
    schema_tokens: int

# A tiny slice of a much larger catalog. In production this is thousands of tools.
catalog: List[Tool] = [
    Tool("pdf_extract", "extract text and tables from pdf invoice documents", 160),
    Tool("table_to_csv", "convert extracted tables into csv files", 140),
    Tool("email_send", "send an email with csv attachments to a recipient", 150),
    Tool("ocr_scan", "read text from scanned invoice images", 150),
    Tool("sheet_read", "read tabular data to export as csv", 130),
    Tool("image_resize", "resize and crop raster images", 120),
    Tool("translate_text", "translate text between languages", 120),
    Tool("calendar_create", "create a calendar event with attendees", 130),
    Tool("weather_lookup", "current weather for a city", 110),
    Tool("sql_query", "run a read-only query against a database", 160),
    Tool("stock_quote", "latest price for a stock ticker", 110),
    Tool("geocode_address", "turn a street address into coordinates", 130),
    Tool("sentiment_score", "rate the sentiment of a passage of text", 120),
    Tool("video_transcode", "re-encode a video into another format", 150),
]

def tokenize(text: str) -> List[str]:
    return [w for w in re.split(r"[^a-z]+", text.lower()) if len(w) > 2]

# Keyword-overlap score in [0, 1], a deterministic stand-in for cosine similarity.
def score(query: str, tool: Tool) -> float:
    q = set(tokenize(query))
    words = tokenize(tool.name.replace("_", " ") + " " + tool.description)
    if not q:
        return 0.0
    hits = len(q.intersection(words))
    return hits / len(q)

# Deterministic half-up rounding via floor, so TS, Python, and Rust agree.
def pct2(s: float) -> str:
    r = int(s * 100 + 0.5)
    return f"{r // 100}.{r % 100:02d}"

def bar(frac: float) -> str:
    cells = 12
    filled = int(frac * cells + 0.5)
    return "[" + "#" * filled + "-" * (cells - filled) + "]"

def main() -> None:
    query = "Convert this invoice PDF to CSV and email it to finance"
    print("=== Tool Retrieval (Tool RAG) ===")
    print(f"query: {query}")
    print(f"catalog: {len(catalog)} tools loaded here (stands in for thousands)")

    ranked = sorted(catalog, key=lambda t: (-score(query, t), t.name))

    print("\nretrieve + rerank (top scores):")
    for tool in ranked[: TOP_K + 2]:
        s = score(query, tool)
        print(f"  {bar(s)} {pct2(s)}  {tool.name}")

    shortlist = [t for t in ranked[:TOP_K] if score(query, t) > 0]
    print(f"\nshortlist: load only top {len(shortlist)} schemas -> [{', '.join(t.name for t in shortlist)}]")

    picked_tokens = sum(t.schema_tokens for t in shortlist)
    all_tokens = sum(t.schema_tokens for t in catalog)
    print(f"prompt tokens: {picked_tokens} (shortlist) vs {all_tokens} (whole catalog)")
    print(f"saved: {all_tokens - picked_tokens} tokens by not loading irrelevant schemas")

    # Model selects an ordered pipeline from the small, focused schema set.
    names = {t.name for t in shortlist}
    pipeline = [n for n in ["pdf_extract", "table_to_csv", "email_send"] if n in names]
    print(f"\nmodel selects pipeline: {' -> '.join(pipeline)}")
    print("  pdf_extract  -> tables pulled from the invoice")
    print("  table_to_csv -> rows written to invoice.csv")
    print("  email_send   -> invoice.csv delivered to finance")
    print("\nresult: correct tools chosen from a focused shortlist, at a fraction of the token cost")

if __name__ == "__main__":
    main()
```

## References

- RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection via Retrieval-Augmented Generation - https://arxiv.org/abs/2505.03275
- MCP-Zero: Active Tool Discovery for Autonomous LLM Agents - https://arxiv.org/abs/2506.01056

---
Source: https://agentic-design.ai/patterns/tool-use/tool-retrieval (extraction: free-pack, content sha256 81e704929bc0…)
