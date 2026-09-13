# CLAUDE.md — agentic-patterns-catalog

## What this is
A catalog of 288 agentic design patterns that agents query to pick a pattern for a task. Sub-project
SP1 of a larger program (spec §1). Spec: `docs/superpowers/specs/2026-09-12-agentic-patterns-catalog-design.md`.
Decisions: `docs/adr/`. Read the spec before changing a data shape.

## Design properties (spec §2)
useful, secure, repeatable, composable, deterministic-where-it-matters.
- The deterministic path (`get_pattern`, facet filter, BM25) runs on a bare install. Embeddings,
  Postgres, OAuth, OPA are extras.
- Every answer carries provenance. An empty result says "No pattern matches in the catalog."
- Published numbers are generated, never typed: `docs/data/*.json` holds results; prose cites them.
- One command verifies everything: `uv run catalog verify`.

## Conventions
- Pydantic models in `model.py` are the source of truth; `schema/*.json` is generated from them.
- Everything under `skills/agentic-patterns/generated/` and `catalog/index.json` is compiled. Never hand-edit.
- Facet values come from `catalog/vocab/facets.json` only. Adding a value = data change + schema regeneration.
- The 277 non-pack records are gitignored. Never commit site prose for them.
- Write docs, docstrings, comments and commit messages in ASD-STE100 Simplified Technical English.
- Before every commit: `uv run --extra lint ruff check .` and `uv run pytest`.
- Commits: one author, no assistant attribution. Every commit ships tests or says why it cannot.

## Toolchain
Python 3.14 + uv. `uv sync --extra dev`; `uv run pytest`; `uv run catalog …`.
New dependencies that the deterministic path does not need go in an extra.
