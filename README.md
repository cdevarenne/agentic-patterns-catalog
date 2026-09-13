# agentic-patterns-catalog

A catalog of agentic design patterns, structured so an agent can be handed a task and get the
few patterns that apply — with provenance on every field.

Status: design accepted (see `docs/adr/0001-catalog-design.md`); implementation in progress.

## Attribution and license

Code and enrichment in this repository: MIT (see `LICENSE`).

The pattern names, taxonomy and the 11 `tool-use` records under `catalog/patterns/tool-use/` come
from the agentic-design.ai free patterns pack, © KORTEXYA SAS, whose README says: "Free to use in
your own projects, and free to pass on to a colleague. The catalog itself stays © KORTEXYA SAS; do
not republish it as your own." The other 277 records are built locally from a personal mirror and
are not distributed with this repository (`catalog extract` rebuilds them). The 24 category
records under `catalog/categories/` are site prose as well: they are rebuilt locally in the same
way and are not distributed.

## Quick start

```sh
uv sync --extra dev
uv run pytest
uv run catalog --help
```

Without uv: `python3.14 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`.

## Commands

| Command | What it does |
|---|---|
| `catalog extract --mirror DIR` | build the 288 records from a local mirror (277 stay untracked) |
| `catalog seed` | write the 11 free-pack records |
| `catalog index` | write `catalog/index.json` |
| `catalog compile [--local]` | write `CATALOG.md`, `CATALOG-full.md`, guides, sheets |
| `catalog select "task" [--facet k=v] [-k N]` | pick patterns for a task; `--json` for the full envelope |
| `catalog eval` | golden set → `docs/data/eval.json` |
| `catalog verify` | every check; exit 1 on any problem |

## Provenance

Every record carries `provenance.source` (url, mirror date, extraction method, content hash) and, once
enriched, `provenance.enrichment` per selection field (method, model, date, reviewer). Every `select`
answer returns the record's provenance, the retrieval path per hit, and the catalog version.
