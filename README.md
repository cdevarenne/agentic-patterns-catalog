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
are not distributed with this repository (`catalog extract` rebuilds them).

## Quick start

```sh
uv sync --extra dev
uv run pytest
uv run catalog --help
```

Without uv: `python3.14 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`.
