# agentic-patterns-catalog

A catalog of agentic design patterns, structured so an agent can be handed a task and get the
few patterns that apply — with provenance on every field.

Status: design accepted (see `docs/adr/0001-catalog-design.md`); implementation in progress.

## Attribution and license

Code and enrichment in this repository: MIT (see `LICENSE`).

The pattern names, taxonomy and the 11 `tool-use` records come from the agentic-design.ai free
patterns pack, © KORTEXYA SAS, whose README says: "Free to use in your own projects, and free to
pass on to a colleague. The catalog itself stays © KORTEXYA SAS; do not republish it as your own."
This repository tracks all 288 records, because each record holds the project's own enrichment
(identity, selection, provenance) rather than the site prose itself. Site prose lives only in the
gitignored cache under `var/content/`. For the 11 pack records the licensed prose is tracked in
`data/pack/patterns.json` and `catalog seed` caches it; for the other 277 records `catalog extract`
fills the cache from a local mirror, and that prose is never distributed. The 24 category records
under `catalog/categories/` are also site prose, cached the same way and not distributed.

## Quick start

```sh
uv sync --extra dev
uv run catalog extract --mirror DIR   # fills the var/content/ cache for 277 records
uv run catalog seed                   # caches the 11 pack records from data/pack/patterns.json, not the mirror
uv run pytest
uv run catalog --help
```

Running from another directory: `CATALOG_ROOT=/path/to/checkout uv run catalog verify` (ADR-0004).

Without uv: `python3.14 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`.

## Commands

| Command | What it does |
|---|---|
| `catalog extract --mirror DIR` | build the records and cache the site content from a local mirror (skips the 11 pack records) |
| `catalog seed` | write the 11 free-pack records and cache their content from `data/pack/patterns.json` |
| `catalog index` | write `catalog/index.json` |
| `catalog compile [--local]` | write `CATALOG.md`, `CATALOG-full.md`, guides, sheets |
| `catalog select "task" [--facet k=v] [-k N]` | pick patterns for a task; `--json` for the full envelope |
| `catalog sync-pg [--embeddings MODEL]` | load the Postgres mirror from the files (extra pg) |
| `catalog serve [--http]` | run the MCP server (stdio by default; `--http` for Streamable HTTP with Google login) |
| `catalog eval` | golden set → `docs/data/eval.json` |
| `catalog calibrate` | evidence for the off-topic gate → `docs/data/floor-calibration.json` |
| `catalog verify` | every check; exit 1 on any problem |

## MCP server

Run the catalog as a Model Context Protocol server over stdio or Streamable HTTP.
Local clients like Claude Code can run the stdio server directly using `.mcp.json`.
For remote HTTP access with Google OAuth authentication and access control, see `docs/auth.md`.

## Postgres mirror (optional)

You can mirror the catalog files into a local PostgreSQL database with `pgvector`.
Install the `pg` extra:

```sh
uv sync --extra pg
```

Set the database connection string:

```sh
export CATALOG_PG_DSN=postgresql:///agentic_patterns_catalog
```

Load the database from the files:

```sh
catalog sync-pg --embeddings BAAI/bge-small-en-v1.5
```

The files on disk remain the source of truth.
When `CATALOG_PG_DSN` is set, `catalog verify` compares the database against the files and reports any drift.
To configure the MCP server to read from Postgres, set `CATALOG_STORE=pg`. To write activity events to Postgres, set `CATALOG_LEDGER=pg`.

## Provenance

Every record carries `provenance.source` (url, mirror date, extraction method, content hash) and, once
enriched, `provenance.enrichment` per selection field (method, model, date, reviewer). Every `select`
answer returns the record's provenance, the retrieval path per hit, and the catalog version.
Without the `embed` extra there is no semantic arm and `select` cannot detect off-topic queries; it
returns its best lexical matches with their scores.
