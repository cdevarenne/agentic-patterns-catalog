# Plan B — Catalog Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the catalog's data layer end to end — schema, extraction from the local mirror, pack seed, file store, compiled Markdown views, hybrid `select`, evaluation, and `verify` — so `uv run catalog select "route requests by intent"` returns provenance-carrying hits and `uv run catalog verify` passes.

**Architecture:** A `src/` Python package with one module per responsibility (`model`, `vocab`, `rsc`, `details`, `extract`, `seed`, `store`, `compile`, `retrieval`, `evaluate`, `verify`, `cli`). Pydantic models are the source of truth; JSON files under `catalog/` are the store; every other artifact is compiled from them. Retrieval is facet filter → BM25 ∥ local embeddings → RRF. Nothing here needs a network, a key, or a database.

**Tech Stack:** Python 3.14, uv, pydantic v2, rank-bm25, beautifulsoup4, numpy (via rank-bm25), fastembed (extra `embed`), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-12-agentic-patterns-catalog-design.md` §2–§5, §7, §9, §11 (build steps 2–5 of §14). Decision record: `docs/adr/0001-catalog-design.md`.

**Not in this plan (own plans, written after this one lands):** Plan C — MCP server, AuthN/AuthZ, `Ledger`, Postgres (spec §6, §4.6). Plan D — Claude Code skill, Python and Kotlin agents (§10). Plan E — enrichment CLI and the two recipes (§8, §4.5).

## Global Constraints

- Python **3.14** pinned in `.python-version`; managed with **uv**; `uv.lock` committed.
- `[project] dependencies` = `pydantic`, `rank-bm25`, `beautifulsoup4` only. Everything else is an extra: `embed` (fastembed), `dev` (pytest), `lint` (ruff). (Spec §11 lists `pg`, `opa`, `mcp`, `agent` — those extras are added by Plans C/D.)
- Before **every** commit: `uv run --extra lint ruff check .` passes and `uv run pytest` passes.
- The 277 non-pack records under `catalog/patterns/**` are gitignored; only `catalog/patterns/tool-use/` is committed. Never commit site prose for the other 277 (spec §7).
- All JSON written by the code: `json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"`.
- Pattern `id` is the bare slug; file path is `catalog/patterns/<category>/<id>.json`.
- Field names under `content` match the free pack's `patterns.json` where the pack has the field.
- Docstrings and comments in ASD-STE100 style: short sentences, active voice, one idea each.
- Commit messages: one-line subject; ≤3 body lines only for a non-obvious why; no assistant attribution.
- Tests never read the real mirror unless it exists; tests that need it are marked `@pytest.mark.mirror` and skip otherwise.

## File Structure

```
agentic-patterns-catalog/
├── pyproject.toml, .python-version, uv.lock, README.md, CLAUDE.md, .env.example
├── catalog/
│   ├── vocab/facets.json             controlled facet vocabulary (Task 2)
│   ├── patterns/<category>/<id>.json 288 locally, 11 committed (Tasks 6–7)
│   ├── categories/<id>.json          24 committed (Task 6)
│   ├── recipes/                      empty until Plan E
│   └── index.json                    (Task 8)
├── data/pack/patterns.json           verbatim copy of the free pack data + LICENSE-NOTE.md (Task 7)
├── schema/pattern.schema.json, category.schema.json, recipe.schema.json   generated (Task 3)
├── eval/tasks.jsonl, eval/thresholds.json                                  (Task 11)
├── docs/data/eval.json, docs/data/smoke.json                               generated (Tasks 11, 13)
├── skills/agentic-patterns/generated/{CATALOG.md, CATALOG-full.md, guides/, sheets/}  (Task 9)
├── src/agentic_patterns_catalog/
│   ├── __init__.py, paths.py         repo-relative paths (Task 1)
│   ├── vocab.py                      load + check facet vocabulary (Task 2)
│   ├── model.py, schema.py           pydantic models, content hash, schema generation (Task 3)
│   ├── rsc.py                        React Server Components stream parser (Task 4)
│   ├── details.py                    hidden HTML details block parser (Task 5)
│   ├── extract.py                    page → Pattern + Category records (Task 6)
│   ├── seed.py                       pack JSON → Pattern records (Task 7)
│   ├── store.py                      Store protocol, FileStore, index (Task 8)
│   ├── compile.py                    CATALOG.md, CATALOG-full.md, guides, sheets, budgets (Task 9)
│   ├── retrieval.py                  Selector: facets → BM25 ∥ semantic → RRF (Task 10)
│   ├── evaluate.py                   golden set runner → docs/data/eval.json (Task 11)
│   ├── verify.py                     all checks (Task 12)
│   └── cli.py                        `catalog` subcommands (grows in each task)
└── tests/
    ├── conftest.py, fixtures/page.html, fixtures/pack.json
    └── test_<module>.py per module
```

---

### Task 1: Repository scaffold and CLI skeleton

**Files:**
- Create: `pyproject.toml`, `.python-version`, `README.md`, `CLAUDE.md`, `.env.example`, `src/agentic_patterns_catalog/__init__.py`, `src/agentic_patterns_catalog/paths.py`, `src/agentic_patterns_catalog/cli.py`, `tests/conftest.py`, `tests/test_cli.py`
- Modify: `.gitignore` (add `var/`, `catalog/index.json` stays tracked)

**Interfaces:**
- Produces: `paths.ROOT, CATALOG_DIR, PATTERNS_DIR, CATEGORIES_DIR, RECIPES_DIR, VOCAB_PATH, INDEX_PATH, SCHEMA_DIR, DATA_DIR, GENERATED_DIR, EVAL_TASKS, EVAL_THRESHOLDS, EMBEDDINGS_DIR: Path`; `cli.main(argv: list[str] | None = None) -> int`; `cli.register(name)` decorator used by later tasks to add subcommands.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from agentic_patterns_catalog import cli


def test_help_lists_subcommands(capsys) -> None:
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "catalog" in out


def test_unknown_subcommand_is_usage_error() -> None:
    assert cli.main(["does-not-exist"]) == 2
```

`tests/conftest.py`:
```python
"""Shared fixtures. The real mirror is optional: tests that need it skip when it is absent."""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MIRROR = Path("/opt/devel/DevMoi/agentic-design-mirror/pages/raw/patterns")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "mirror: needs the local agentic-design mirror")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if MIRROR.exists():
        return
    skip = pytest.mark.skip(reason=f"mirror not found at {MIRROR}")
    for item in items:
        if "mirror" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def mirror() -> Path:
    return MIRROR
```

- [ ] **Step 2: Create the project files**

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "agentic-patterns-catalog"
version = "0.1.0"
description = "A provenance-carrying catalog of agentic design patterns, selectable by agents."
readme = "README.md"
license = "MIT"
requires-python = ">=3.14"
dependencies = [
    "pydantic>=2.12",
    "rank-bm25>=0.2.2",
    "beautifulsoup4>=4.13",
]

[project.optional-dependencies]
dev = ["pytest>=8"]
lint = ["ruff>=0.16"]
# Semantic arm of `select`. Optional so a bare install stays free of ONNX runtimes.
embed = ["fastembed>=0.7"]

[project.scripts]
catalog = "agentic_patterns_catalog.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

`.python-version`: `3.14`

`src/agentic_patterns_catalog/__init__.py`: `"""Agentic patterns catalog."""` (one line).

`src/agentic_patterns_catalog/paths.py`:
```python
"""Repository-relative paths. The package is installed editable, so the repo root is two levels up."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "catalog"
PATTERNS_DIR = CATALOG_DIR / "patterns"
CATEGORIES_DIR = CATALOG_DIR / "categories"
RECIPES_DIR = CATALOG_DIR / "recipes"
VOCAB_PATH = CATALOG_DIR / "vocab" / "facets.json"
INDEX_PATH = CATALOG_DIR / "index.json"
EMBEDDINGS_DIR = CATALOG_DIR / "embeddings"
SCHEMA_DIR = ROOT / "schema"
DATA_DIR = ROOT / "docs" / "data"
GENERATED_DIR = ROOT / "skills" / "agentic-patterns" / "generated"
EVAL_TASKS = ROOT / "eval" / "tasks.jsonl"
EVAL_THRESHOLDS = ROOT / "eval" / "thresholds.json"
PACK_JSON = ROOT / "data" / "pack" / "patterns.json"
SITE = "https://agentic-design.ai"
```

`src/agentic_patterns_catalog/cli.py`:
```python
"""`catalog` command line. Each module registers its own subcommand with `register`."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

Handler = Callable[[argparse.Namespace], int]
_COMMANDS: dict[str, tuple[str, Callable[[argparse.ArgumentParser], None], Handler]] = {}


def register(name: str, help_text: str) -> Callable[[Callable[[argparse.ArgumentParser], Handler]], None]:
    """Register `name` as a subcommand. The decorated function adds arguments and returns the handler."""
    def wrap(configure: Callable[[argparse.ArgumentParser], Handler]) -> None:
        holder: dict[str, Handler] = {}

        def configure_and_capture(parser: argparse.ArgumentParser) -> None:
            holder["handler"] = configure(parser)

        _COMMANDS[name] = (help_text, configure_and_capture, lambda ns: holder["handler"](ns))
    return wrap


def build_parser() -> argparse.ArgumentParser:
    # Import for side effects: each module registers its subcommand.
    from agentic_patterns_catalog import commands  # noqa: F401

    parser = argparse.ArgumentParser(prog="catalog", description="Agentic patterns catalog tools.")
    sub = parser.add_subparsers(dest="command", metavar="command")
    for name, (help_text, configure, _) in sorted(_COMMANDS.items()):
        configure(sub.add_parser(name, help=help_text))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as e:  # argparse exits 0 for --help and 2 for usage errors
        return int(e.code or 0)
    if ns.command is None:
        parser.print_help()
        return 0
    return _COMMANDS[ns.command][2](ns)


if __name__ == "__main__":
    sys.exit(main())
```

`src/agentic_patterns_catalog/commands.py` (grows one import per task):
```python
"""Imports every module that registers a `catalog` subcommand."""
```

`.env.example`:
```
# Nothing is needed for extract/compile/select/verify. Plan C adds the OAuth variables;
# Plan E decides the enrichment provider (Claude Code by default, no key).
```

`README.md` (initial; Task 13 completes it):
```markdown
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
```

`CLAUDE.md`:
```markdown
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
```

Append to `.gitignore`:
```
var/
```

- [ ] **Step 3: Install and run the tests to verify they fail**

Run: `cd /opt/devel/DevMoi/agentic-patterns-catalog && uv sync --extra dev --extra lint && uv run pytest -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.commands'` is **not** expected — the empty `commands.py` exists — so both tests should already pass. If `test_help_lists_subcommands` fails because `--help` printed nothing, check that `main` returns `e.code or 0`.

- [ ] **Step 4: Run tests, ruff; commit**

Run: `uv run pytest -q && uv run --extra lint ruff check .`
Expected: `2 passed`, `All checks passed!`

```bash
git add -A
git commit -m "Scaffold package, CLI skeleton, README and CLAUDE.md"
```

---

### Task 2: Facet vocabulary

**Files:**
- Create: `catalog/vocab/facets.json`, `src/agentic_patterns_catalog/vocab.py`, `tests/test_vocab.py`

**Interfaces:**
- Produces: `vocab.FACET_NAMES: tuple[str, ...]`; `vocab.load_vocab(path: Path = VOCAB_PATH) -> dict[str, list[str]]`; `vocab.unknown_facet_values(facets: dict[str, str | None], vocab: dict[str, list[str]]) -> list[str]` (entries like `"scale=galaxy"`).

- [ ] **Step 1: Write the failing tests**

`tests/test_vocab.py`:
```python
import json
from pathlib import Path

import pytest

from agentic_patterns_catalog import vocab


def test_committed_vocab_has_every_facet_with_unique_values() -> None:
    v = vocab.load_vocab()
    assert set(v) == set(vocab.FACET_NAMES)
    for name, values in v.items():
        assert values, name
        assert len(values) == len(set(values)), name


def test_initial_values_match_the_spec() -> None:
    v = vocab.load_vocab()
    assert v["scale"] == ["single-agent", "multi-agent", "fleet"]
    assert v["maturity"] == ["research", "emerging", "production"]


def test_missing_facet_is_an_error(tmp_path: Path) -> None:
    p = tmp_path / "facets.json"
    p.write_text(json.dumps({"scale": ["x"]}))
    with pytest.raises(ValueError, match="lacks"):
        vocab.load_vocab(p)


def test_unknown_values_are_reported_by_facet() -> None:
    v = vocab.load_vocab()
    bad = vocab.unknown_facet_values({"scale": "galaxy", "maturity": "production", "token_cost": None}, v)
    assert bad == ["scale=galaxy"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_vocab.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.vocab'`

- [ ] **Step 3: Create the vocabulary and the module**

`catalog/vocab/facets.json`:
```json
{
  "latency_cost": ["none", "adds-1-llm-call", "adds-n-llm-calls", "async-only"],
  "maturity": ["research", "emerging", "production"],
  "risk_class": ["misroute", "data-leak", "unsafe-action", "cost-runaway", "quality-drift", "none"],
  "scale": ["single-agent", "multi-agent", "fleet"],
  "token_cost": ["low", "medium", "high"]
}
```

`src/agentic_patterns_catalog/vocab.py`:
```python
"""Controlled facet vocabulary. One data file; the schema, Postgres and rego derive from it."""
from __future__ import annotations

import json
from pathlib import Path

from .paths import VOCAB_PATH

FACET_NAMES = ("scale", "latency_cost", "token_cost", "risk_class", "maturity")


def load_vocab(path: Path = VOCAB_PATH) -> dict[str, list[str]]:
    """Read facets.json. Every facet must be present with unique, non-empty values."""
    vocab: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8"))
    missing = sorted(set(FACET_NAMES) - set(vocab))
    if missing:
        raise ValueError(f"{path} lacks facets {missing}")
    for name, values in vocab.items():
        if not values or len(values) != len(set(values)):
            raise ValueError(f"facet {name!r}: values must be non-empty and unique")
    return vocab


def unknown_facet_values(facets: dict[str, str | None], vocab: dict[str, list[str]]) -> list[str]:
    """`facet=value` entries that are set but not in the vocabulary."""
    return [f"{k}={v}" for k, v in facets.items() if v is not None and v not in vocab.get(k, [])]
```

- [ ] **Step 4: Run tests, ruff; commit**

Run: `uv run pytest -q && uv run --extra lint ruff check .`
Expected: `6 passed`.

```bash
git add -A
git commit -m "Add controlled facet vocabulary as a data file"
```

---

### Task 3: Models, content hash, and generated JSON Schema

**Files:**
- Create: `src/agentic_patterns_catalog/model.py`, `src/agentic_patterns_catalog/schema.py`, `schema/pattern.schema.json`, `schema/category.schema.json`, `schema/recipe.schema.json`, `tests/test_model.py`, `tests/test_schema.py`
- Modify: `src/agentic_patterns_catalog/commands.py`

**Interfaces:**
- Produces (model): `Tldr, Flow, Content, Facets, Relation, Selection, Source, Enrichment, Provenance, Pattern, ImplementationGuide, Category, RecipeStep, Recipe` (pydantic, `extra="forbid"`); `SELECTION_FIELDS: tuple[str, ...]`; `Pattern.reviewed: bool` property; `content_hash(content: Content) -> str`; `dumps(model) -> str` (canonical JSON text for files).
- Produces (schema): `generate_schemas(vocab) -> dict[str, dict]` keyed `pattern|category|recipe`; `write_schemas(schema_dir) -> None`; `schemas_match(schema_dir) -> list[str]` (names that differ); subcommand `catalog schema [--check]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_model.py`:
```python
import pytest
from pydantic import ValidationError

from agentic_patterns_catalog.model import (
    Content, Enrichment, Pattern, Provenance, Source, Tldr, content_hash, dumps,
)


def make_pattern(**over) -> Pattern:
    content = Content(description="Routes by content.", tldr=Tldr(what="w", when="n", watchOut="o"))
    base = dict(
        id="content-based-routing", name="Content-Based Routing", category="routing",
        complexity="medium", content=content,
        provenance=Provenance(source=Source(url="https://agentic-design.ai/patterns/routing/content-based-routing",
                                            extraction="rsc-payload", content_sha256=content_hash(content))),
    )
    base.update(over)
    return Pattern(**base)


def test_content_hash_is_stable_and_order_independent() -> None:
    a = Content(description="d", tldr=Tldr(what="w", when="n", watchOut="o"), features=["x"])
    b = Content(tldr=Tldr(watchOut="o", when="n", what="w"), description="d", features=["x"])
    assert content_hash(a) == content_hash(b)
    assert len(content_hash(a)) == 64


def test_content_hash_changes_when_content_changes() -> None:
    a = Content(description="d", tldr=Tldr(what="w", when="n", watchOut="o"))
    b = Content(description="d2", tldr=Tldr(what="w", when="n", watchOut="o"))
    assert content_hash(a) != content_hash(b)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Tldr(what="w", when="n", watchOut="o", extra="no")  # type: ignore[call-arg]


def test_reviewed_requires_every_selection_field_to_have_a_reviewer() -> None:
    p = make_pattern()
    assert p.reviewed is False
    done = Enrichment(method="human", date="2026-09-12", reviewed_by="cdevarenne")
    p.provenance.enrichment = {
        f: done for f in ("problem_signals", "preconditions", "contraindications", "facets", "relations")
    }
    assert p.reviewed is True
    p.provenance.enrichment["facets"] = Enrichment(method="llm-draft", model="claude-opus-5", date="2026-09-12")
    assert p.reviewed is False


def test_dumps_is_canonical_json_with_trailing_newline() -> None:
    text = dumps(make_pattern())
    assert text.endswith("}\n")
    assert '"category": "routing"' in text
    assert text.index('"category"') < text.index('"complexity"')  # keys sorted
```

`tests/test_schema.py`:
```python
import json
from pathlib import Path

from agentic_patterns_catalog import schema, vocab
from agentic_patterns_catalog.paths import SCHEMA_DIR


def test_generated_schema_embeds_the_vocabulary() -> None:
    s = schema.generate_schemas(vocab.load_vocab())["pattern"]
    scale = s["$defs"]["Facets"]["properties"]["scale"]
    assert {"type": "string", "enum": ["single-agent", "multi-agent", "fleet"]} in scale["anyOf"]
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_committed_schemas_equal_generated() -> None:
    assert schema.schemas_match(SCHEMA_DIR) == []


def test_write_then_match_roundtrip(tmp_path: Path) -> None:
    schema.write_schemas(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "category.schema.json", "pattern.schema.json", "recipe.schema.json",
    ]
    assert schema.schemas_match(tmp_path) == []
    (tmp_path / "recipe.schema.json").write_text(json.dumps({"changed": True}))
    assert schema.schemas_match(tmp_path) == ["recipe"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_model.py tests/test_schema.py -q`
Expected: `ModuleNotFoundError` for `model` and `schema`.

- [ ] **Step 3: Write the models**

`src/agentic_patterns_catalog/model.py`:
```python
"""Pydantic models: the source of truth for every record shape. `schema/*.json` is generated from here."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["pattern", "technique", "benchmark", "tool"]
RelationType = Literal["alternative_to", "composes_with", "requires", "precedes"]
Extraction = Literal["rsc-payload", "free-pack"]
EnrichmentMethod = Literal["llm-draft", "human", "derived"]

SELECTION_FIELDS = ("problem_signals", "preconditions", "contraindications", "facets", "relations")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Tldr(Strict):
    what: str
    when: str
    watchOut: str


class Flow(Strict):
    """The pattern's mechanism diagram. Nodes, edges and steps pass through unchanged."""
    title: str | None = None
    description: str | None = None
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []


class Content(Strict):
    """Source content. Field names follow the free pack's patterns.json where it has the field."""
    description: str
    tldr: Tldr
    abbr: str | None = None
    features: list[str] = []
    useCases: list[str] = []
    example: str | None = None
    code: dict[str, str] = {}
    references: list[str] = []
    flow: Flow | None = None
    details: dict[str, list[str]] = {}


class Facets(Strict):
    """Values must come from catalog/vocab/facets.json; `verify` checks that."""
    scale: str | None = None
    latency_cost: str | None = None
    token_cost: str | None = None
    risk_class: str | None = None
    maturity: str | None = None


class Relation(Strict):
    type: RelationType
    target: str
    prefer_when: str | None = None


class Selection(Strict):
    problem_signals: list[str] = []
    preconditions: list[str] = []
    contraindications: list[str] = []
    facets: Facets = Field(default_factory=Facets)
    relations: list[Relation] = []


class Source(Strict):
    url: str
    mirrored_at: str | None = None
    extraction: Extraction
    content_sha256: str


class Enrichment(Strict):
    method: EnrichmentMethod
    model: str | None = None
    date: str
    reviewed_by: str | None = None


class Provenance(Strict):
    source: Source
    enrichment: dict[str, Enrichment] = {}


class Pattern(Strict):
    id: str
    name: str
    category: str
    kind: Kind = "pattern"
    complexity: str
    content: Content
    selection: Selection = Field(default_factory=Selection)
    provenance: Provenance

    @property
    def reviewed(self) -> bool:
        """True when every selection field has a human reviewer recorded."""
        enrichment = self.provenance.enrichment
        return all(f in enrichment and bool(enrichment[f].reviewed_by) for f in SELECTION_FIELDS)


class ImplementationGuide(Strict):
    whenToUse: list[str] = []
    bestPractices: list[str] = []
    commonPitfalls: list[str] = []


class Category(Strict):
    id: str
    name: str
    description: str
    detailedDescription: str | None = None
    whyImportant: str | None = None
    implementationGuide: ImplementationGuide | None = None
    technique_ids: list[str] = []
    provenance: Source


class RecipeStep(Strict):
    order: int
    pattern_id: str
    role: str
    binding_notes: str | None = None


class Recipe(Strict):
    id: str
    name: str
    use_case: str
    steps: list[RecipeStep]
    source_documents: list[str] = []
    provenance: Enrichment


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(content: Content) -> str:
    """SHA-256 of the canonical JSON of `content`. Same content, same hash, in any key order."""
    return hashlib.sha256(_canonical(content.model_dump(mode="json")).encode("utf-8")).hexdigest()


def dumps(model: BaseModel) -> str:
    """Canonical file text for a record: sorted keys, two-space indent, trailing newline."""
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
```

The camelCase field names (`watchOut`, `useCases`, `whenToUse`, …) are deliberate: they match the free pack's JSON so its records load unchanged. Ruff's default rule set does not flag them.

- [ ] **Step 4: Write schema generation**

`src/agentic_patterns_catalog/schema.py`:
```python
"""JSON Schema files generated from the models. `verify` fails when the committed files differ."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import vocab as vocab_mod
from .cli import register
from .model import Category, Pattern, Recipe
from .paths import SCHEMA_DIR

DRAFT = "https://json-schema.org/draft/2020-12/schema"
_MODELS = {"pattern": Pattern, "category": Category, "recipe": Recipe}


def generate_schemas(vocab: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """One schema per record type. Facet enums are injected from the vocabulary file."""
    out: dict[str, dict[str, Any]] = {}
    for name, model in _MODELS.items():
        s = model.model_json_schema()
        s = {"$schema": DRAFT, "$id": f"https://github.com/cdevarenne/agentic-patterns-catalog/schema/{name}.schema.json", **s}
        facets = s.get("$defs", {}).get("Facets", {}).get("properties", {})
        for facet, values in vocab.items():
            if facet in facets:
                facets[facet] = {"anyOf": [{"type": "string", "enum": list(values)}, {"type": "null"}], "default": None}
        out[name] = s
    return out


def _text(s: dict[str, Any]) -> str:
    return json.dumps(s, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_schemas(schema_dir: Path = SCHEMA_DIR) -> None:
    schema_dir.mkdir(parents=True, exist_ok=True)
    for name, s in generate_schemas(vocab_mod.load_vocab()).items():
        (schema_dir / f"{name}.schema.json").write_text(_text(s), encoding="utf-8")


def schemas_match(schema_dir: Path = SCHEMA_DIR) -> list[str]:
    """Names of schemas whose committed file differs from a fresh generation (or is missing)."""
    bad = []
    for name, s in generate_schemas(vocab_mod.load_vocab()).items():
        path = schema_dir / f"{name}.schema.json"
        if not path.exists() or path.read_text(encoding="utf-8") != _text(s):
            bad.append(name)
    return bad


@register("schema", "write schema/*.json from the models (--check: compare only)")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--check", action="store_true", help="exit 1 if committed schemas are stale")

    def run(ns: argparse.Namespace) -> int:
        if ns.check:
            stale = schemas_match()
            print("schemas up to date" if not stale else f"stale schemas: {', '.join(stale)}")
            return 1 if stale else 0
        write_schemas()
        print(f"wrote {len(_MODELS)} schemas to {SCHEMA_DIR}")
        return 0
    return run
```

Add to `commands.py`: `from . import schema  # noqa: F401`.

- [ ] **Step 5: Generate the schema files and run the tests**

Run: `uv run catalog schema && uv run pytest tests/test_model.py tests/test_schema.py -q`
Expected: `wrote 3 schemas to …/schema`, then `8 passed`.

- [ ] **Step 6: Run everything, ruff; commit**

Run: `uv run pytest -q && uv run --extra lint ruff check .`

```bash
git add -A
git commit -m "Add record models, content hash and generated JSON Schemas"
```

---

### Task 4: RSC stream parser

**Files:**
- Create: `src/agentic_patterns_catalog/rsc.py`, `tests/test_rsc.py`, `tests/fixtures/page.html`

**Interfaces:**
- Produces: `rsc.rsc_rows(html: str) -> dict[str, Any]` — rows of the React Server Components stream keyed by row id (JSON rows decoded; `T` text rows and reference rows as `str`); `rsc.find_dicts(node, pred) -> Iterator[dict]`; `rsc.page_props(html) -> dict` — the props dict holding `tldr` and `selectedTechnique`, or raises `ValueError`.

Background for the implementer: Next.js streams React Server Components as `self.__next_f.push([1, "<chunk>"])` script calls. Concatenating the chunks gives lines of the form `<hexid>:<payload>`. A payload starting with `T` is a text row: `T<hexlen>,<raw bytes>` where **the length counts UTF-8 bytes** and the text may contain newlines. Other payloads are JSON (`[`, `{`, …) or reference strings (`I[...]`, `HL[...]`). Parsing character-wise breaks on emoji; parse bytes.

- [ ] **Step 1: Create the synthetic fixture**

`tests/fixtures/page.html` (synthetic; mimics the real layout, contains no site prose). Note the `T` row with an emoji, which is the case the byte-length rule covers:
```html
<!DOCTYPE html><html><head><title>Fixture</title></head><body>
<div hidden id="S:3"><section><h2>Core Mechanism</h2><div><p>Matches capability to request.</p></div></section><section><h2>Workflow / Steps</h2><ol><li>Analyze the request.</li><li>Match a handler.</li></ol></section><section><h2>Key Features</h2><div><div><span>Registry of handler capabilities</span></div></div></section><section><h3>When to Use</h3><div><h4>Use When</h4><ul><li>• Many handlers exist</li></ul><h4>Avoid When</h4><ul><li>• One handler only</li></ul></div></section><section><h2>References &amp; Further Reading</h2><p>ignored</p></section></div><script>$RC("B:3","S:3")</script>
<script>self.__next_f.push([1,"1:HL[\"/_next/static/css/x.css\",\"style\"]\n"])</script>
<script>self.__next_f.push([1,"2:Tc,Hello 🌍!!\n3:[\"$\",\"div\",null,{\"children\":\"$L4\"}]\n"])</script>
<script>self.__next_f.push([1,"4:[\"$\",\"main\",null,{\"tldr\":{\"what\":\"Matches request needs to handler capabilities.\",\"when\":\"Handlers differ in ability.\",\"watchOut\":\"Stale capability data.\"},\"selectedTechnique\":{\"id\":\"fixture-routing\",\"name\":\"Fixture Routing\",\"abbr\":\"FR\",\"category\":\"routing\",\"complexity\":\"medium\",\"description\":\"Routes by capability.\",\"features\":[\"Capability registry\"],\"useCases\":[\"triage\"],\"example\":\"Request -> handler\",\"references\":[\"A paper - https://example.org/p\"]},\"codeExamples\":{\"python\":\"print(1)\\n\",\"typescript\":\"console.log(1)\\n\"},\"flowScenario\":{\"id\":\"f\",\"title\":\"Flow\",\"description\":\"d\",\"initialNodes\":[{\"id\":\"n1\"}],\"initialEdges\":[{\"id\":\"e1\",\"source\":\"n1\",\"target\":\"n1\"}],\"steps\":[{\"id\":\"s1\",\"title\":\"t\",\"description\":\"d\"}]},\"categories\":[{\"id\":\"routing\",\"name\":\"Routing\",\"description\":\"Dispatch patterns.\",\"detailedDescription\":\"Longer.\",\"whyImportant\":\"Because.\",\"implementationGuide\":{\"whenToUse\":[\"Many handlers\"],\"bestPractices\":[\"Keep rules small\"],\"commonPitfalls\":[\"Stale rules\"]},\"techniques\":[{\"id\":\"fixture-routing\",\"name\":\"Fixture Routing\"}]}]}]\n"])</script>
</body></html>
```
`Tc` is the byte length in hex: `len("Hello 🌍!!".encode()) == 12`. The test below asserts the decoded text, so a wrong length fails loudly.

- [ ] **Step 2: Write the failing tests**

`tests/test_rsc.py`:
```python
from pathlib import Path

import pytest

from agentic_patterns_catalog import rsc


def test_rows_decode_json_and_text_rows(fixtures: Path) -> None:
    rows = rsc.rsc_rows((fixtures / "page.html").read_text(encoding="utf-8"))
    assert rows["2"] == "Hello 🌍!!"          # T row, byte length, emoji
    assert rows["3"][1] == "div"               # JSON row after the text row is intact
    assert rows["1"].startswith("HL[")         # reference row kept as text


def test_page_props_finds_tldr_and_technique(fixtures: Path) -> None:
    props = rsc.page_props((fixtures / "page.html").read_text(encoding="utf-8"))
    assert props["selectedTechnique"]["id"] == "fixture-routing"
    assert props["tldr"]["what"].startswith("Matches")
    assert len(props["categories"]) == 1


def test_page_props_raises_without_props() -> None:
    with pytest.raises(ValueError, match="no pattern props"):
        rsc.page_props("<html><script>self.__next_f.push([1,\"1:[]\\n\"])</script></html>")


@pytest.mark.mirror
def test_every_mirrored_page_has_props(mirror: Path) -> None:
    pages = sorted(mirror.glob("*/*.html"))
    assert len(pages) == 288
    for page in pages:
        props = rsc.page_props(page.read_text(encoding="utf-8"))
        assert props["selectedTechnique"]["id"] == page.stem
        assert props["selectedTechnique"]["category"] == page.parent.name
        assert len(props["categories"]) == 24
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rsc.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.rsc'`

- [ ] **Step 4: Implement the parser**

`src/agentic_patterns_catalog/rsc.py`:
```python
"""Parser for the React Server Components (RSC) stream that Next.js embeds in each page.

Next.js emits `self.__next_f.push([1, "<chunk>"])` script calls. The joined chunks are rows of
`<hexid>:<payload>`. A `T` payload is text: `T<hexlen>,<bytes>`; the length counts UTF-8 bytes and
the text may contain newlines. Other payloads are JSON or reference strings. Parse bytes, not
characters: emoji in a text row shift every later slice otherwise.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)
_ROW_ID = re.compile(rb"([0-9a-f]+):")
_JSON_START = b'[{"0123456789tfn-'


def rsc_text(html: str) -> str:
    """The joined RSC chunks as one string. Each chunk is a JSON string literal."""
    return "".join(json.loads(c) for c in _CHUNK.findall(html))


def rsc_rows(html: str) -> dict[str, Any]:
    """Rows keyed by id. JSON rows are decoded; text and reference rows stay strings."""
    data = rsc_text(html).encode("utf-8")
    decoder = json.JSONDecoder()
    rows: dict[str, Any] = {}
    pos, n = 0, len(data)

    def next_line(p: int) -> int:
        nl = data.find(b"\n", p)
        return n if nl < 0 else nl + 1

    while pos < n:
        m = _ROW_ID.match(data, pos)
        if not m:
            pos = next_line(pos)
            continue
        rid, pos = m.group(1).decode(), m.end()
        if pos >= n:
            break
        head = data[pos:pos + 1]
        if head == b"T":
            comma = data.index(b",", pos)
            length = int(data[pos + 1:comma], 16)
            start = comma + 1
            rows[rid] = data[start:start + length].decode("utf-8", "replace")
            pos = start + length
        elif head in _JSON_START:
            end = data.find(b"\n", pos)
            line = data[pos:(n if end < 0 else end)].decode("utf-8")
            try:
                rows[rid], used = decoder.raw_decode(line)
            except json.JSONDecodeError:
                pos = next_line(pos)
                continue
            pos += len(line[:used].encode("utf-8"))
        else:
            end = data.find(b"\n", pos)
            rows[rid] = data[pos:(n if end < 0 else end)].decode("utf-8", "replace")
            pos = next_line(pos)
            continue
        if pos < n and data[pos:pos + 1] == b"\n":
            pos += 1
    return rows


def find_dicts(node: Any, pred: Callable[[dict[str, Any]], bool]) -> Iterator[dict[str, Any]]:
    """Depth-first: every dict in `node` for which `pred` is true."""
    if isinstance(node, dict):
        if pred(node):
            yield node
        for value in node.values():
            yield from find_dicts(value, pred)
    elif isinstance(node, list):
        for value in node:
            yield from find_dicts(value, pred)


def page_props(html: str) -> dict[str, Any]:
    """The props dict of a pattern page: it carries `tldr` and `selectedTechnique`."""
    rows = rsc_rows(html)
    props = next(find_dicts(rows, lambda d: "tldr" in d and "selectedTechnique" in d), None)
    if props is None:
        raise ValueError("no pattern props (tldr + selectedTechnique) in the RSC stream")
    return props
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_rsc.py -q -m "not mirror"` then `uv run pytest tests/test_rsc.py -q`
Expected: 3 passed without the mirror; 4 passed with it (the mirror test takes ~20 s).

- [ ] **Step 6: Ruff; commit**

```bash
uv run --extra lint ruff check . && git add -A
git commit -m "Parse the RSC stream with byte-accurate text rows"
```

---

### Task 5: Details block parser

**Files:**
- Create: `src/agentic_patterns_catalog/details.py`, `tests/test_details.py`

**Interfaces:**
- Produces: `details.parse_details(html: str) -> dict[str, list[str]]` — `{normalized heading: [item texts]}` from the hidden block that ends with "References & Further Reading"; sub-headings (h4) become `parent.child` keys; `details.normalize_heading(text: str) -> str`.

Background: every page has a `<div hidden id="S:n">` block with per-pattern detail sections. Deep template (35 pages): h2 `Core Mechanism`, `Workflow / Steps`, `Best Practices`, `When NOT to Use`, `Common Pitfalls`, `Key Features`, `KPIs / Success Metrics`, `Token / Resource Usage`, `Best Use Cases`. Standard template (253): h3 `30-Second Overview`, `Quick Implementation`, `Do's & Don'ts`, `When to Use` (with h4 `Use When` / `Avoid When`), `Key Metrics`, `Top Use Cases`. Items sit in `li`, `p`, or leaf `span`/`div` elements. Both templates end with h2 `References & Further Reading` (references come from the RSC props instead).

- [ ] **Step 1: Write the failing tests**

`tests/test_details.py`:
```python
from pathlib import Path

import pytest

from agentic_patterns_catalog import details


def test_normalize_heading() -> None:
    assert details.normalize_heading("KPIs / Success Metrics") == "kpis"
    assert details.normalize_heading("Do's & Don'ts") == "dos_and_donts"
    assert details.normalize_heading("30-Second Overview") == "overview_30s"
    assert details.normalize_heading("When NOT to Use") == "when_not_to_use"
    assert details.normalize_heading("Workflow / Steps") == "workflow_steps"


def test_parse_fixture_covers_li_p_span_and_h4(fixtures: Path) -> None:
    d = details.parse_details((fixtures / "page.html").read_text(encoding="utf-8"))
    assert d["core_mechanism"] == ["Matches capability to request."]
    assert d["workflow_steps"] == ["Analyze the request.", "Match a handler."]
    assert d["key_features"] == ["Registry of handler capabilities"]
    assert d["when_to_use.use_when"] == ["Many handlers exist"]      # bullet stripped
    assert d["when_to_use.avoid_when"] == ["One handler only"]
    assert "references_and_further_reading" not in d


def test_page_without_details_block_gives_empty_dict() -> None:
    assert details.parse_details("<html><body><p>x</p></body></html>") == {}


@pytest.mark.mirror
def test_mirror_templates_yield_expected_keys(mirror: Path) -> None:
    deep = details.parse_details((mirror / "routing" / "capability-routing.html").read_text(encoding="utf-8"))
    assert {"core_mechanism", "workflow_steps", "when_not_to_use", "common_pitfalls", "kpis"} <= set(deep)
    standard = details.parse_details(
        (mirror / "evaluation-monitoring" / "cyberseceval3.html").read_text(encoding="utf-8"))
    assert {"overview_30s", "quick_implementation", "dos_and_donts", "when_to_use.use_when"} <= set(standard)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_details.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.details'`

- [ ] **Step 3: Implement the parser**

`src/agentic_patterns_catalog/details.py`:
```python
"""Parser for the per-pattern detail sections streamed as a hidden HTML block."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

_HEADINGS = ("h2", "h3", "h4")
_ALIASES = {
    "kpis_success_metrics": "kpis",
    "do_s_and_don_ts": "dos_and_donts",
    "30_second_overview": "overview_30s",
}
_STOP = "references_and_further_reading"
_MIN_LEAF_TEXT = 15


def normalize_heading(text: str) -> str:
    """`KPIs / Success Metrics` → `kpis`; `Do's & Don'ts` → `dos_and_donts`."""
    key = text.lower().replace("&", " and ")
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    return _ALIASES.get(key, key)


def _clean(text: str) -> str:
    return re.sub(r"^[•\-–—*]\s*", "", " ".join(text.split())).strip()


def _segment(heading: Tag) -> list[Tag]:
    """Tags after `heading` up to the next heading of the same or a higher level."""
    level = int(heading.name[1])
    out: list[Tag] = []
    for node in heading.next_elements:
        if isinstance(node, Tag) and node.name in _HEADINGS and int(node.name[1]) <= level:
            break
        if isinstance(node, Tag):
            out.append(node)
    return out


def _items(segment: list[Tag]) -> list[str]:
    """Texts of li/p in the segment; else texts of leaf span/div that look like items."""
    primary = [_clean(t.get_text(" ", strip=True)) for t in segment if t.name in ("li", "p")]
    primary = [t for t in primary if t]
    if primary:
        return list(dict.fromkeys(primary))
    leaves = [
        _clean(t.get_text(" ", strip=True))
        for t in segment
        if t.name in ("span", "div") and not t.find_all(True) and len(t.get_text(strip=True)) >= _MIN_LEAF_TEXT
    ]
    return list(dict.fromkeys(t for t in leaves if t))


def _details_block(soup: BeautifulSoup) -> Tag | None:
    for block in soup.find_all("div", hidden=True):
        if any(normalize_heading(h.get_text(" ", strip=True)) == _STOP for h in block.find_all("h2")):
            return block
    return None


def parse_details(html: str) -> dict[str, list[str]]:
    """`{normalized heading: [items]}` for the hidden details block; `{}` when a page has none."""
    soup = BeautifulSoup(html, "html.parser")
    block = _details_block(soup)
    if block is None:
        return {}
    out: dict[str, list[str]] = {}
    parent_key: dict[int, str] = {}
    for heading in block.find_all(_HEADINGS):
        level = int(heading.name[1])
        key = normalize_heading(heading.get_text(" ", strip=True))
        if key == _STOP:
            break
        parent_key[level] = key
        if level == 4 and 3 in parent_key:
            key = f"{parent_key[3]}.{key}"
        items = _items(_segment(heading))
        if level < 4 and heading.find_next(_HEADINGS) is not None and not items:
            continue  # a container heading whose content lives under its h4 children
        if items and key not in out:
            out[key] = items
    return out
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_details.py -q`
Expected: 3 passed (4 with the mirror). If `when_to_use.use_when` is missing, check that the h4 loop sees `parent_key[3]` set by the preceding h3 (`When to Use`).

- [ ] **Step 5: Ruff; commit**

```bash
uv run --extra lint ruff check . && git add -A
git commit -m "Parse per-pattern detail sections from the hidden HTML block"
```

---

### Task 6: Extractor — page → Pattern + Category records

**Files:**
- Create: `src/agentic_patterns_catalog/extract.py`, `tests/test_extract.py`, `catalog/categories/` (24 files, committed)
- Modify: `src/agentic_patterns_catalog/commands.py`

**Interfaces:**
- Consumes: `rsc.page_props`, `details.parse_details`, `model.*`, `paths.SITE`.
- Produces: `extract.extract_page(html: str, *, url: str, mirrored_at: str | None) -> tuple[Pattern, list[Category]]`; `extract.extract_mirror(mirror_dir: Path, out_dir: Path, *, force: bool = False) -> ExtractReport` with fields `written: int, skipped_pack: int, categories: int, empty_details: list[str]`; subcommand `catalog extract --mirror DIR [--out DIR] [--force]`.

Rules: `content.useCases` comes from `selectedTechnique.useCases` (the page-level `useCases` is a global list, not pattern-specific). `mirrored_at` is the raw file's mtime as an ISO date. A record whose existing file has `extraction == "free-pack"` is skipped unless `--force` (the committed pack records win). Category records are rewritten every run.

- [ ] **Step 1: Write the failing tests**

`tests/test_extract.py`:
```python
import json
from pathlib import Path

import pytest

from agentic_patterns_catalog import extract
from agentic_patterns_catalog.model import Pattern


def test_extract_page_builds_pattern_and_categories(fixtures: Path) -> None:
    html = (fixtures / "page.html").read_text(encoding="utf-8")
    p, cats = extract.extract_page(html, url="https://agentic-design.ai/patterns/routing/fixture-routing",
                                   mirrored_at="2026-09-12")
    assert p.id == "fixture-routing" and p.category == "routing" and p.complexity == "medium"
    assert p.content.tldr.watchOut == "Stale capability data."
    assert p.content.useCases == ["triage"]                 # technique-level, not the page list
    assert p.content.code == {"python": "print(1)\n", "typescript": "console.log(1)\n"}
    assert p.content.flow is not None and p.content.flow.nodes == [{"id": "n1"}]
    assert p.content.details["core_mechanism"] == ["Matches capability to request."]
    assert p.provenance.source.extraction == "rsc-payload"
    assert len(p.provenance.source.content_sha256) == 64
    assert [c.id for c in cats] == ["routing"]
    assert cats[0].implementationGuide is not None
    assert cats[0].implementationGuide.whenToUse == ["Many handlers"]
    assert cats[0].technique_ids == ["fixture-routing"]


def test_extract_mirror_writes_files_and_skips_pack_records(fixtures: Path, tmp_path: Path) -> None:
    mirror = tmp_path / "mirror" / "routing"
    mirror.mkdir(parents=True)
    (mirror / "fixture-routing.html").write_text((fixtures / "page.html").read_text(encoding="utf-8"))
    out = tmp_path / "catalog"
    existing = out / "patterns" / "routing" / "fixture-routing.json"
    existing.parent.mkdir(parents=True)
    existing.write_text(json.dumps({"provenance": {"source": {"extraction": "free-pack"}}}))

    report = extract.extract_mirror(tmp_path / "mirror", out)
    assert report.skipped_pack == 1 and report.written == 0 and report.categories == 1
    assert json.loads(existing.read_text())["provenance"]["source"]["extraction"] == "free-pack"

    report = extract.extract_mirror(tmp_path / "mirror", out, force=True)
    assert report.written == 1
    Pattern.model_validate_json(existing.read_text())
    assert (out / "categories" / "routing.json").exists()


@pytest.mark.mirror
def test_real_mirror_extracts_288_patterns_and_24_categories(mirror: Path, tmp_path: Path) -> None:
    report = extract.extract_mirror(mirror, tmp_path / "catalog")
    assert report.written == 288 and report.categories == 24
    assert len(report.empty_details) < 10, report.empty_details
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_extract.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.extract'`

- [ ] **Step 3: Implement the extractor**

`src/agentic_patterns_catalog/extract.py`:
```python
"""Build Pattern and Category records from mirrored pages."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cli import register
from .details import parse_details
from .model import (
    Category, Content, Flow, ImplementationGuide, Pattern, Provenance, Source, Tldr, content_hash, dumps,
)
from .paths import CATALOG_DIR, SITE
from .rsc import page_props


@dataclass
class ExtractReport:
    written: int = 0
    skipped_pack: int = 0
    categories: int = 0
    empty_details: list[str] = field(default_factory=list)


def _flow(scenario: dict[str, Any] | None) -> Flow | None:
    if not scenario:
        return None
    return Flow(
        title=scenario.get("title"), description=scenario.get("description"),
        nodes=scenario.get("initialNodes") or [], edges=scenario.get("initialEdges") or [],
        steps=scenario.get("steps") or [],
    )


def _category(raw: dict[str, Any], mirrored_at: str | None) -> Category:
    guide = raw.get("implementationGuide")
    payload = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Category(
        id=raw["id"], name=raw["name"], description=raw.get("description", ""),
        detailedDescription=raw.get("detailedDescription"), whyImportant=raw.get("whyImportant"),
        implementationGuide=ImplementationGuide(
            whenToUse=guide.get("whenToUse") or [], bestPractices=guide.get("bestPractices") or [],
            commonPitfalls=guide.get("commonPitfalls") or []) if guide else None,
        technique_ids=[t["id"] for t in raw.get("techniques") or [] if "id" in t],
        provenance=Source(url=f"{SITE}/patterns/{raw['id']}", mirrored_at=mirrored_at,
                          extraction="rsc-payload", content_sha256=hashlib.sha256(payload).hexdigest()),
    )


def extract_page(html: str, *, url: str, mirrored_at: str | None) -> tuple[Pattern, list[Category]]:
    """One page → its Pattern and the category records the page embeds."""
    props = page_props(html)
    tech = props["selectedTechnique"]
    content = Content(
        description=tech.get("description", ""), tldr=Tldr(**{k: props["tldr"][k] for k in ("what", "when", "watchOut")}),
        abbr=tech.get("abbr"), features=tech.get("features") or [], useCases=tech.get("useCases") or [],
        example=tech.get("example"), code={k: v for k, v in (props.get("codeExamples") or {}).items() if isinstance(v, str)},
        references=[r for r in tech.get("references") or [] if isinstance(r, str)],
        flow=_flow(props.get("flowScenario")), details=parse_details(html),
    )
    pattern = Pattern(
        id=tech["id"], name=tech["name"], category=tech["category"], complexity=tech.get("complexity") or "unknown",
        content=content,
        provenance=Provenance(source=Source(url=url, mirrored_at=mirrored_at, extraction="rsc-payload",
                                            content_sha256=content_hash(content))),
    )
    return pattern, [_category(c, mirrored_at) for c in props.get("categories") or []]


def _is_pack_record(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text(encoding="utf-8"))["provenance"]["source"]["extraction"] == "free-pack"
    except (KeyError, ValueError, TypeError):
        return False


def extract_mirror(mirror_dir: Path, out_dir: Path = CATALOG_DIR, *, force: bool = False) -> ExtractReport:
    """Every `<category>/<slug>.html` under `mirror_dir` → `out_dir/patterns/…` and `out_dir/categories/…`."""
    report = ExtractReport()
    categories: dict[str, Category] = {}
    for page in sorted(mirror_dir.glob("*/*.html")):
        mirrored_at = dt.datetime.fromtimestamp(page.stat().st_mtime, dt.UTC).date().isoformat()
        url = f"{SITE}/patterns/{page.parent.name}/{page.stem}"
        pattern, cats = extract_page(page.read_text(encoding="utf-8"), url=url, mirrored_at=mirrored_at)
        for c in cats:
            categories.setdefault(c.id, c)
        target = out_dir / "patterns" / pattern.category / f"{pattern.id}.json"
        if _is_pack_record(target) and not force:
            report.skipped_pack += 1
            continue
        if not pattern.content.details:
            report.empty_details.append(pattern.id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dumps(pattern), encoding="utf-8")
        report.written += 1
    for c in categories.values():
        path = out_dir / "categories" / f"{c.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(c), encoding="utf-8")
    report.categories = len(categories)
    return report


@register("extract", "build pattern and category records from a local mirror")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--mirror", type=Path, required=True, help="…/agentic-design-mirror/pages/raw/patterns")
    parser.add_argument("--out", type=Path, default=CATALOG_DIR)
    parser.add_argument("--force", action="store_true", help="overwrite records seeded from the free pack")

    def run(ns: argparse.Namespace) -> int:
        r = extract_mirror(ns.mirror, ns.out, force=ns.force)
        print(f"written {r.written}, skipped pack records {r.skipped_pack}, categories {r.categories}, "
              f"empty details {len(r.empty_details)}")
        return 0
    return run
```

Add to `commands.py`: `from . import extract  # noqa: F401`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_extract.py -q`
Expected: 2 passed without the mirror, 3 with it. If `Pattern` validation fails on a real page, the error names the field; fix the coercion in `extract_page`, never loosen the model.

- [ ] **Step 5: Run the real extraction and commit the categories only**

Run: `uv run catalog extract --mirror /opt/devel/DevMoi/agentic-design-mirror/pages/raw/patterns`
Expected: `written 288, skipped pack records 0, categories 24, empty details <n>`.

Run: `git status --short | head` — `catalog/patterns/**` must be absent except nothing yet under `tool-use/` (Task 7 seeds it; the extracted `tool-use` files are rsc-payload records — **do not commit them**; Task 7 replaces them).

```bash
git add src tests catalog/categories
git commit -m "Extract pattern and category records from the mirror"
```

Then remove the 11 extracted tool-use files so Task 7 can seed cleanly: `rm catalog/patterns/tool-use/*.json`.

---

### Task 7: Pack seed — the 11 committed records

**Files:**
- Create: `data/pack/patterns.json` (verbatim copy of `…/patterns-pack-free/data/patterns.json`), `data/pack/LICENSE-NOTE.md`, `src/agentic_patterns_catalog/seed.py`, `tests/test_seed.py`, `tests/fixtures/pack.json`
- Modify: `src/agentic_patterns_catalog/commands.py`

**Interfaces:**
- Produces: `seed.seed_from_pack(pack: dict) -> list[Pattern]`; `seed.write_seed(pack_path: Path, out_dir: Path) -> int`; subcommand `catalog seed [--pack FILE] [--out DIR]`.

- [ ] **Step 1: Copy the pack data and write the license note**

```bash
mkdir -p data/pack
cp /opt/devel/DevMoi/agentic-design-mirror/patterns-pack-free/data/patterns.json data/pack/patterns.json
```

`data/pack/LICENSE-NOTE.md`:
```markdown
# Origin of `patterns.json`

Verbatim copy of `data/patterns.json` from the agentic-design.ai **free patterns pack**
(11 patterns, category Tool Use), downloaded 2026-09-12. © KORTEXYA SAS.

The pack's README states: "Free to use in your own projects, and free to pass on to a colleague.
The catalog itself stays © KORTEXYA SAS; do not republish it as your own."

This repository uses the file as sample data for the 11 `tool-use` records and cites it as the
origin in each record's `provenance.source`. Nothing else from agentic-design.ai is distributed here.
```

`tests/fixtures/pack.json` — a two-record subset in the pack's shape (write the two objects by taking `patterns[0]` and `patterns[1]` from the copied file with `python3 -c "import json;d=json.load(open('data/pack/patterns.json'));d['patterns']=d['patterns'][:2];d['patternCount']=2;print(json.dumps(d,indent=2))" > tests/fixtures/pack.json`).

- [ ] **Step 2: Write the failing tests**

`tests/test_seed.py`:
```python
import json
from pathlib import Path

from agentic_patterns_catalog import seed
from agentic_patterns_catalog.model import Pattern
from agentic_patterns_catalog.paths import PACK_JSON, PATTERNS_DIR


def test_seed_maps_pack_fields_onto_the_model(fixtures: Path) -> None:
    pack = json.loads((fixtures / "pack.json").read_text(encoding="utf-8"))
    patterns = seed.seed_from_pack(pack)
    assert len(patterns) == 2
    p = patterns[0]
    assert p.id == pack["patterns"][0]["id"] and p.category == "tool-use"
    assert p.content.tldr.what == pack["patterns"][0]["tldr"]["what"]
    assert p.content.code.keys() == pack["patterns"][0]["code"].keys()
    assert p.provenance.source.extraction == "free-pack"
    assert p.provenance.source.url == f"https://agentic-design.ai/patterns/tool-use/{p.id}"


def test_write_seed_creates_files(fixtures: Path, tmp_path: Path) -> None:
    n = seed.write_seed(fixtures / "pack.json", tmp_path)
    assert n == 2
    files = sorted((tmp_path / "patterns" / "tool-use").glob("*.json"))
    assert len(files) == 2
    Pattern.model_validate_json(files[0].read_text(encoding="utf-8"))


def test_committed_tool_use_records_match_the_pack() -> None:
    pack = json.loads(PACK_JSON.read_text(encoding="utf-8"))
    committed = {p.stem for p in (PATTERNS_DIR / "tool-use").glob("*.json")}
    assert committed == {p["id"] for p in pack["patterns"]}
    for path in (PATTERNS_DIR / "tool-use").glob("*.json"):
        assert Pattern.model_validate_json(path.read_text(encoding="utf-8")).provenance.source.extraction == "free-pack"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_seed.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.seed'`

- [ ] **Step 4: Implement the seed**

`src/agentic_patterns_catalog/seed.py`:
```python
"""Seed Pattern records from the free pack's patterns.json (the 11 licensed sample records)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .cli import register
from .model import Content, Pattern, Provenance, Source, Tldr, content_hash, dumps
from .paths import CATALOG_DIR, PACK_JSON, SITE


def _pattern(raw: dict[str, Any]) -> Pattern:
    content = Content(
        description=raw["description"], tldr=Tldr(**{k: raw["tldr"][k] for k in ("what", "when", "watchOut")}),
        features=raw.get("features") or [], useCases=raw.get("useCases") or [], example=raw.get("example"),
        code=raw.get("code") or {}, references=raw.get("references") or [],
    )
    return Pattern(
        id=raw["id"], name=raw["name"], category=raw["category"], complexity=raw.get("complexity") or "unknown",
        content=content,
        provenance=Provenance(source=Source(url=f"{SITE}/patterns/{raw['category']}/{raw['id']}",
                                            extraction="free-pack", content_sha256=content_hash(content))),
    )


def seed_from_pack(pack: dict[str, Any]) -> list[Pattern]:
    return [_pattern(raw) for raw in pack["patterns"]]


def write_seed(pack_path: Path = PACK_JSON, out_dir: Path = CATALOG_DIR) -> int:
    """Write one file per pack record. Returns the count."""
    patterns = seed_from_pack(json.loads(pack_path.read_text(encoding="utf-8")))
    for p in patterns:
        path = out_dir / "patterns" / p.category / f"{p.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(p), encoding="utf-8")
    return len(patterns)


@register("seed", "write the free-pack records into the catalog")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--pack", type=Path, default=PACK_JSON)
    parser.add_argument("--out", type=Path, default=CATALOG_DIR)

    def run(ns: argparse.Namespace) -> int:
        print(f"seeded {write_seed(ns.pack, ns.out)} records")
        return 0
    return run
```

Add to `commands.py`: `from . import seed  # noqa: F401`.

- [ ] **Step 5: Seed, run the tests, commit**

Run: `uv run catalog seed && uv run pytest tests/test_seed.py -q`
Expected: `seeded 11 records`, `3 passed`. `git status` shows exactly 11 files under `catalog/patterns/tool-use/` (the `.gitignore` allows only that directory).

```bash
uv run --extra lint ruff check . && git add -A
git commit -m "Seed the 11 free-pack records with provenance and license note"
```

Now re-run the extractor so the local tree holds all 288 (the 11 pack records are skipped):
`uv run catalog extract --mirror /opt/devel/DevMoi/agentic-design-mirror/pages/raw/patterns`
Expected: `written 277, skipped pack records 11, categories 24 …`.

---

### Task 8: Store protocol, FileStore, index

**Files:**
- Create: `src/agentic_patterns_catalog/store.py`, `tests/test_store.py`, `catalog/index.json` (generated, committed)
- Modify: `src/agentic_patterns_catalog/commands.py`

**Interfaces:**
- Produces: `store.Store` (Protocol: `get(id) -> Pattern`, `all() -> list[Pattern]`, `put(p) -> None`, `categories() -> list[Category]`, `recipes() -> list[Recipe]`); `store.FileStore(root: Path = CATALOG_DIR)`; `store.build_index(store) -> dict`; `store.write_index(store, path=INDEX_PATH) -> dict`; `store.catalog_version(root=ROOT) -> str`; subcommand `catalog index`.
- Index shape: `{"generated_from": <catalog_version>, "patterns": {id: {"category", "kind", "content_sha256", "extraction", "reviewed"}}, "categories": [ids], "recipes": [ids]}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:
```python
import json
from pathlib import Path

import pytest

from agentic_patterns_catalog import store
from agentic_patterns_catalog.model import Content, Pattern, Provenance, Source, Tldr, content_hash


def _p(id: str, category: str = "routing") -> Pattern:
    c = Content(description=f"{id} d", tldr=Tldr(what="w", when="n", watchOut="o"))
    return Pattern(id=id, name=id.title(), category=category, complexity="low", content=c,
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


@pytest.fixture
def fs(tmp_path: Path) -> store.FileStore:
    s = store.FileStore(tmp_path)
    for p in (_p("b-pat"), _p("a-pat"), _p("c-pat", "memory-management")):
        s.put(p)
    return s


def test_put_writes_under_category_and_all_is_sorted_by_id(fs: store.FileStore, tmp_path: Path) -> None:
    assert (tmp_path / "patterns" / "routing" / "a-pat.json").exists()
    assert [p.id for p in fs.all()] == ["a-pat", "b-pat", "c-pat"]


def test_get_unknown_id_raises_key_error(fs: store.FileStore) -> None:
    with pytest.raises(KeyError):
        fs.get("nope")
    assert fs.get("a-pat").category == "routing"


def test_index_lists_every_pattern_with_hash_and_review_state(fs: store.FileStore, tmp_path: Path) -> None:
    idx = store.write_index(fs, tmp_path / "index.json")
    assert set(idx["patterns"]) == {"a-pat", "b-pat", "c-pat"}
    assert idx["patterns"]["a-pat"]["reviewed"] is False
    assert idx["patterns"]["a-pat"]["extraction"] == "rsc-payload"
    assert json.loads((tmp_path / "index.json").read_text())["patterns"]["c-pat"]["category"] == "memory-management"


def test_catalog_version_is_a_short_string() -> None:
    v = store.catalog_version()
    assert isinstance(v, str) and 4 <= len(v) <= 20
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_store.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.store'`

- [ ] **Step 3: Implement the store**

`src/agentic_patterns_catalog/store.py`:
```python
"""Where records live. FileStore is the default and needs nothing installed."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Protocol

from .cli import register
from .model import Category, Pattern, Recipe, dumps
from .paths import CATALOG_DIR, INDEX_PATH, ROOT


class Store(Protocol):
    def get(self, id: str) -> Pattern: ...
    def all(self) -> list[Pattern]: ...
    def put(self, pattern: Pattern) -> None: ...
    def categories(self) -> list[Category]: ...
    def recipes(self) -> list[Recipe]: ...


class FileStore:
    """One JSON file per record under `root`. Reads are sorted by id so every consumer is deterministic."""

    def __init__(self, root: Path = CATALOG_DIR) -> None:
        self.root = root

    def _pattern_paths(self) -> list[Path]:
        return sorted((self.root / "patterns").glob("*/*.json"), key=lambda p: p.stem)

    def all(self) -> list[Pattern]:
        return [Pattern.model_validate_json(p.read_text(encoding="utf-8")) for p in self._pattern_paths()]

    def get(self, id: str) -> Pattern:
        matches = list((self.root / "patterns").glob(f"*/{id}.json"))
        if not matches:
            raise KeyError(id)
        return Pattern.model_validate_json(matches[0].read_text(encoding="utf-8"))

    def put(self, pattern: Pattern) -> None:
        path = self.root / "patterns" / pattern.category / f"{pattern.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(pattern), encoding="utf-8")

    def categories(self) -> list[Category]:
        return [Category.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted((self.root / "categories").glob("*.json"))]

    def recipes(self) -> list[Recipe]:
        return [Recipe.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted((self.root / "recipes").glob("*.json"))]


def catalog_version(root: Path = ROOT) -> str:
    """Short git sha of the last commit touching catalog/, or 'uncommitted' outside git."""
    try:
        sha = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%h", "--", "catalog"],
                             capture_output=True, text=True, check=True).stdout.strip()
        return sha or "uncommitted"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "uncommitted"


def build_index(store: Store) -> dict[str, Any]:
    return {
        "generated_from": catalog_version(),
        "patterns": {
            p.id: {
                "category": p.category, "kind": p.kind,
                "content_sha256": p.provenance.source.content_sha256,
                "extraction": p.provenance.source.extraction, "reviewed": p.reviewed,
            }
            for p in store.all()
        },
        "categories": [c.id for c in store.categories()],
        "recipes": [r.id for r in store.recipes()],
    }


def write_index(store: Store, path: Path = INDEX_PATH) -> dict[str, Any]:
    idx = build_index(store)
    path.write_text(json.dumps(idx, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return idx


@register("index", "write catalog/index.json (the freshness and coverage ledger)")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)

    def run(ns: argparse.Namespace) -> int:
        idx = write_index(FileStore(ns.root), ns.root / "index.json")
        print(f"indexed {len(idx['patterns'])} patterns, {len(idx['categories'])} categories")
        return 0
    return run
```

Add to `commands.py`: `from . import store  # noqa: F401`.

- [ ] **Step 4: Run the tests, write the index, commit**

Run: `uv run pytest tests/test_store.py -q && uv run catalog index`
Expected: `4 passed`; `indexed 288 patterns, 24 categories` locally.

Note: the committed `index.json` lists all 288 ids with hashes — that is metadata, not prose, and the spec (§4.3) wants it committed. CI (11 records) will regenerate a smaller index; Task 12's `verify` compares the index against the files present, so both states verify.

```bash
uv run --extra lint ruff check . && git add -A
git commit -m "Add FileStore and the catalog index"
```

---

### Task 9: Compiled views — CATALOG.md, CATALOG-full.md, guides, sheets

**Files:**
- Create: `src/agentic_patterns_catalog/compile.py`, `tests/test_compile.py`, `skills/agentic-patterns/generated/` (committed output)
- Modify: `src/agentic_patterns_catalog/commands.py`, `.gitignore` (add `skills/agentic-patterns/generated/local/`)

**Interfaces:**
- Consumes: `store.Store`.
- Produces: `compile.token_estimate(text: str) -> int` (= `len(text) // 4`); `compile.BUDGETS = {"CATALOG.md": 2000, "CATALOG-full.md": 16000}`; `compile.compile_all(store, *, local: bool = False) -> dict[str, str]` mapping relative output path → text; `compile.write_all(store, out_dir: Path, *, local: bool) -> list[Path]`; `compile.over_budget(outputs: dict[str, str]) -> list[str]`; subcommand `catalog compile [--out DIR] [--local]`.
- Line rules (spec §7): `CATALOG.md` one line per category: `- **<id>** — <description> — <n> patterns`. `CATALOG-full.md` one line per pattern: pack records `- <id> — <tldr.what> — use when: <tldr.when>`; others `- <id> — <name> — <first problem_signal>` when present, else `- <id> — <name>`; with `local=True` every record uses the tldr form. Guides: one per category, opening with the `implementationGuide`, then a table `| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |`, then an "Alternatives" list from `alternative_to` relations with `prefer_when`. Sheets: full reference sheet per **pack** record (all records with `local=True`) in the free pack's Markdown layout: title, `Category | Complexity`, description, "In 30 seconds" bullets, Key features, Use cases, Walkthrough example (fenced `text`), Implementation (first available language, fenced), References.

- [ ] **Step 1: Write the failing tests**

`tests/test_compile.py`:
```python
from pathlib import Path

import pytest

from agentic_patterns_catalog import compile as comp
from agentic_patterns_catalog import store
from agentic_patterns_catalog.model import (
    Category, Content, Enrichment, ImplementationGuide, Pattern, Provenance, Relation, Selection, Source, Tldr,
    content_hash,
)


def _p(id: str, extraction: str = "rsc-payload", **sel) -> Pattern:
    c = Content(description=f"{id} does X.", tldr=Tldr(what=f"{id} what", when=f"{id} when", watchOut="w"),
                features=["f1"], useCases=["u1"], example="ex", code={"python": "print(1)"}, references=["r - u"])
    return Pattern(id=id, name=id.title(), category="routing", complexity="low", content=c, selection=Selection(**sel),
                   provenance=Provenance(source=Source(url="u", extraction=extraction, content_sha256=content_hash(c))))


@pytest.fixture
def fs(tmp_path: Path) -> store.FileStore:
    s = store.FileStore(tmp_path)
    s.put(_p("pack-one", "free-pack"))
    s.put(_p("plain-two"))
    s.put(_p("rich-three", problem_signals=["requests span domains"],
             relations=[Relation(type="alternative_to", target="plain-two", prefer_when="rules are known")]))
    (tmp_path / "categories").mkdir()
    cat = Category(id="routing", name="Routing", description="Dispatch.",
                   implementationGuide=ImplementationGuide(whenToUse=["many handlers"]),
                   technique_ids=["pack-one", "plain-two", "rich-three"],
                   provenance=Source(url="u", extraction="rsc-payload", content_sha256="0" * 64))
    (tmp_path / "categories" / "routing.json").write_text(cat.model_dump_json())
    return s


def test_catalog_md_is_one_line_per_category(fs: store.FileStore) -> None:
    out = comp.compile_all(fs)
    assert out["CATALOG.md"].strip().splitlines()[-1] == "- **routing** — Dispatch. — 3 patterns"


def test_full_index_quotes_tldr_only_for_pack_records(fs: store.FileStore) -> None:
    lines = comp.compile_all(fs)["CATALOG-full.md"].splitlines()
    assert "- pack-one — pack-one what — use when: pack-one when" in lines
    assert "- plain-two — Plain-Two" in lines
    assert "- rich-three — Rich-Three — requests span domains" in lines
    assert not any("plain-two what" in line for line in lines)


def test_local_mode_uses_tldr_for_everyone(fs: store.FileStore) -> None:
    lines = comp.compile_all(fs, local=True)["CATALOG-full.md"].splitlines()
    assert "- plain-two — plain-two what — use when: plain-two when" in lines


def test_guide_has_table_and_alternatives(fs: store.FileStore) -> None:
    guide = comp.compile_all(fs)["guides/routing.md"]
    assert "many handlers" in guide
    assert "| rich-three | Rich-Three | low |" in guide
    assert "rich-three → plain-two: rules are known" in guide


def test_sheets_only_for_pack_records_unless_local(fs: store.FileStore) -> None:
    assert "sheets/pack-one.md" in comp.compile_all(fs)
    assert "sheets/plain-two.md" not in comp.compile_all(fs)
    assert "sheets/plain-two.md" in comp.compile_all(fs, local=True)
    sheet = comp.compile_all(fs)["sheets/pack-one.md"]
    assert sheet.startswith("# Pack-One") and "## In 30 seconds" in sheet and "```python" in sheet


def test_budget_check_names_offenders() -> None:
    assert comp.over_budget({"CATALOG.md": "x" * 4 * 2001, "CATALOG-full.md": "y"}) == ["CATALOG.md"]
    assert comp.token_estimate("abcd" * 10) == 10


def test_write_all_creates_files(fs: store.FileStore, tmp_path: Path) -> None:
    written = comp.write_all(fs, tmp_path / "gen", local=False)
    assert (tmp_path / "gen" / "CATALOG.md").exists()
    assert any(p.name == "routing.md" for p in written)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_compile.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.compile'`

- [ ] **Step 3: Implement the compiler**

`src/agentic_patterns_catalog/compile.py`:
```python
"""Compile agent-facing Markdown from the store. Nothing here is hand-edited."""
from __future__ import annotations

import argparse
from pathlib import Path

from .cli import register
from .model import Category, Pattern
from .paths import CATALOG_DIR, GENERATED_DIR
from .store import FileStore, Store

BUDGETS = {"CATALOG.md": 2000, "CATALOG-full.md": 16000}
FACET_COLUMNS = ("scale", "latency_cost", "token_cost", "risk_class", "maturity")


def token_estimate(text: str) -> int:
    """Rough token count: four characters per token."""
    return len(text) // 4


def _is_pack(p: Pattern) -> bool:
    return p.provenance.source.extraction == "free-pack"


def _full_line(p: Pattern, local: bool) -> str:
    if local or _is_pack(p):
        return f"- {p.id} — {p.content.tldr.what} — use when: {p.content.tldr.when}"
    if p.selection.problem_signals:
        return f"- {p.id} — {p.name} — {p.selection.problem_signals[0]}"
    return f"- {p.id} — {p.name}"


def _catalog_md(categories: list[Category], patterns: list[Pattern]) -> str:
    counts: dict[str, int] = {}
    for p in patterns:
        counts[p.category] = counts.get(p.category, 0) + 1
    lines = ["# Agentic patterns — categories", "",
             "One line per category. Open `guides/<id>.md` or call `select` for patterns.", ""]
    lines += [f"- **{c.id}** — {c.description} — {counts.get(c.id, 0)} patterns" for c in categories]
    return "\n".join(lines) + "\n"


def _full_md(patterns: list[Pattern], local: bool) -> str:
    lines = ["# Agentic patterns — all records", ""]
    lines += [_full_line(p, local) for p in patterns]
    return "\n".join(lines) + "\n"


def _guide(cat: Category, patterns: list[Pattern], by_id: dict[str, Pattern]) -> str:
    lines = [f"# {cat.name} — guide", "", cat.description, ""]
    g = cat.implementationGuide
    if g:
        for title, items in (("When to use", g.whenToUse), ("Best practices", g.bestPractices),
                             ("Common pitfalls", g.commonPitfalls)):
            if items:
                lines += [f"## {title}", ""] + [f"- {i}" for i in items] + [""]
    lines += ["## Patterns", "", "| id | name | complexity | " + " | ".join(FACET_COLUMNS) + " |",
              "|---|---|---|" + "---|" * len(FACET_COLUMNS)]
    for p in patterns:
        facets = [getattr(p.selection.facets, f) or "" for f in FACET_COLUMNS]
        lines.append(f"| {p.id} | {p.name} | {p.complexity} | " + " | ".join(facets) + " |")
    alts = [(p, r) for p in patterns for r in p.selection.relations if r.type == "alternative_to"]
    if alts:
        lines += ["", "## Alternatives", ""]
        for p, r in alts:
            target = by_id.get(r.target)
            name = f"{r.target} ({target.name})" if target else r.target
            lines.append(f"- {p.id} → {name}: {r.prefer_when or 'no preference recorded'}")
    return "\n".join(lines) + "\n"


def _sheet(p: Pattern) -> str:
    c = p.content
    lines = [f"# {p.name}" + (f" ({c.abbr})" if c.abbr else ""), "",
             f"Category: {p.category} | Complexity: {p.complexity}", "", c.description, "",
             "## In 30 seconds", "", f"- **What:** {c.tldr.what}", f"- **When:** {c.tldr.when}",
             f"- **Watch out:** {c.tldr.watchOut}", ""]
    if c.features:
        lines += ["## Key features", ""] + [f"- {f}" for f in c.features] + [""]
    if c.useCases:
        lines += ["## Use cases", ""] + [f"- {u}" for u in c.useCases] + [""]
    if c.example:
        lines += ["## Walkthrough example", "", "> Illustrative scenario from the source; figures are not measurements.",
                  "", "```text", c.example.rstrip(), "```", ""]
    if c.code:
        lang = next(iter(sorted(c.code)))
        lines += [f"## Implementation ({lang})", "", f"```{lang}", c.code[lang].rstrip(), "```", ""]
    if c.references:
        lines += ["## References", ""] + [f"- {r}" for r in c.references] + [""]
    lines += ["---", f"Source: {p.provenance.source.url} (extraction: {p.provenance.source.extraction}, "
              f"content sha256 {p.provenance.source.content_sha256[:12]}…)"]
    return "\n".join(lines) + "\n"


def compile_all(store: Store, *, local: bool = False) -> dict[str, str]:
    """Relative output path → text. `local` may quote tldr for every record; keep that output out of git."""
    patterns = store.all()
    categories = store.categories()
    by_id = {p.id: p for p in patterns}
    out = {"CATALOG.md": _catalog_md(categories, patterns), "CATALOG-full.md": _full_md(patterns, local)}
    for cat in categories:
        out[f"guides/{cat.id}.md"] = _guide(cat, [p for p in patterns if p.category == cat.id], by_id)
    for p in patterns:
        if local or _is_pack(p):
            out[f"sheets/{p.id}.md"] = _sheet(p)
    return out


def over_budget(outputs: dict[str, str]) -> list[str]:
    return [name for name, limit in BUDGETS.items() if name in outputs and token_estimate(outputs[name]) > limit]


def write_all(store: Store, out_dir: Path = GENERATED_DIR, *, local: bool = False) -> list[Path]:
    written = []
    for rel, text in compile_all(store, local=local).items():
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


@register("compile", "write CATALOG.md, CATALOG-full.md, guides and sheets")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)
    parser.add_argument("--out", type=Path, default=None, help="default: skills/agentic-patterns/generated (or …/local with --local)")
    parser.add_argument("--local", action="store_true", help="quote tldr for every record; output is gitignored")

    def run(ns: argparse.Namespace) -> int:
        out_dir = ns.out or (GENERATED_DIR / "local" if ns.local else GENERATED_DIR)
        store = FileStore(ns.root)
        outputs = compile_all(store, local=ns.local)
        for rel, text in outputs.items():
            path = out_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        bad = over_budget(outputs)
        for name in ("CATALOG.md", "CATALOG-full.md"):
            print(f"{name}: ~{token_estimate(outputs[name])} tokens (budget {BUDGETS[name]})")
        print(f"wrote {len(outputs)} files to {out_dir}")
        return 1 if bad else 0
    return run
```

Add to `commands.py`: `from . import compile  # noqa: F401`. Append `skills/agentic-patterns/generated/local/` to `.gitignore`.

- [ ] **Step 4: Run the tests, compile, commit**

Run: `uv run pytest tests/test_compile.py -q && uv run catalog compile`
Expected: `7 passed`; token counts printed under budget; `wrote 288+ files` locally. Inspect `git status`: the committed output includes `CATALOG.md`, `CATALOG-full.md` (277 lines of `id — name`, 11 with tldr), 24 guides, 11 sheets. Open `CATALOG-full.md` and confirm no line other than the 11 pack lines contains site prose.

```bash
uv run --extra lint ruff check . && git add -A
git commit -m "Compile category index, full index, guides and sheets"
```

---

### Task 10: Retrieval — facets → BM25 ∥ semantic → RRF

**Files:**
- Create: `src/agentic_patterns_catalog/retrieval.py`, `tests/test_retrieval.py`
- Modify: `src/agentic_patterns_catalog/commands.py`

**Interfaces:**
- Consumes: `store.Store`, `store.catalog_version`, `paths.EMBEDDINGS_DIR`.
- Produces:
  - `retrieval.Embedder` (Protocol: `name: str`; `embed(texts: list[str]) -> np.ndarray` rows L2-normalized).
  - `retrieval.FastEmbedEmbedder(model_name="BAAI/bge-small-en-v1.5")`, `retrieval.HashEmbedder(dim=256)` (deterministic bag-of-words, for tests and offline fallback), `retrieval.default_embedder() -> Embedder | None` (FastEmbed when importable, else `None`).
  - `retrieval.pattern_text(p: Pattern) -> str`, `retrieval.tokenize(text) -> list[str]`, `retrieval.rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]`.
  - `retrieval.Hit` dataclass: `id, name, category, score_bm25: float | None, score_semantic: float | None, rrf_rank: int, retrieval_path: str, reviewed: bool, provenance: dict, relations: list[dict]`.
  - `retrieval.SelectResult` dataclass: `hits: list[Hit], retrieval_path: str, catalog_version: str, auth: dict, empty_message: str | None`; `.to_dict()`.
  - `retrieval.Selector(patterns, embedder=None, arms=("bm25","semantic"))` with `.select(task, facets=None, k=5, subject="stdio-local") -> SelectResult`; `Selector.from_store(store, embedder=None, arms=…)`.
  - subcommand `catalog select TASK [--facet k=v]... [-k N] [--no-embed] [--json]`.
- Constants: `EMPTY_MESSAGE = "No pattern matches in the catalog."`, `K_RRF = 60`.

- [ ] **Step 1: Write the failing tests**

`tests/test_retrieval.py`:
```python
import pytest

from agentic_patterns_catalog import retrieval as r
from agentic_patterns_catalog.model import (
    Content, Facets, Pattern, Provenance, Relation, Selection, Source, Tldr, content_hash,
)


def _p(id: str, what: str, when: str = "", **sel) -> Pattern:
    c = Content(description=what, tldr=Tldr(what=what, when=when, watchOut="w"))
    return Pattern(id=id, name=id, category="routing", complexity="low", content=c, selection=Selection(**sel),
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


PATTERNS = [
    _p("content-routing", "Classifies request content and routes to a specialised handler.",
       "requests span several domains", facets=Facets(scale="multi-agent")),
    _p("load-balancing", "Spreads requests evenly across identical workers.", "workers are identical",
       facets=Facets(scale="fleet")),
    _p("reflection", "Model critiques and revises its own draft.", "quality matters more than latency"),
]


def test_tokenize_and_pattern_text() -> None:
    assert r.tokenize("Route, requests: by-intent!") == ["route", "requests", "by", "intent"]
    assert "requests span several domains" in r.pattern_text(PATTERNS[0])


def test_rrf_prefers_ids_present_in_both_lists() -> None:
    fused = r.rrf([["a", "b", "c"], ["b", "a"]], k=60)
    assert [i for i, _ in fused][:2] == ["a", "b"] or [i for i, _ in fused][:2] == ["b", "a"]
    assert fused[0][1] > fused[2][1]
    assert r.rrf([["x"], ["x"]])[0][1] == pytest.approx(2 / 61)


def test_bm25_only_select_is_deterministic_and_carries_provenance() -> None:
    sel = r.Selector(PATTERNS, embedder=None)
    res = sel.select("route requests by content to a handler", k=2)
    assert res.retrieval_path == "bm25"
    assert res.hits[0].id == "content-routing"
    assert res.hits[0].score_semantic is None and res.hits[0].retrieval_path == "bm25"
    assert res.hits[0].provenance["source"]["extraction"] == "rsc-payload"
    assert res.empty_message is None
    assert res.hits == sel.select("route requests by content to a handler", k=2).hits


def test_facet_filter_restricts_candidates() -> None:
    sel = r.Selector(PATTERNS, embedder=None)
    res = sel.select("requests", facets={"scale": "fleet"}, k=5)
    assert [h.id for h in res.hits] == ["load-balancing"]


def test_no_lexical_overlap_gives_the_empty_message() -> None:
    res = r.Selector(PATTERNS, embedder=None).select("photosynthesis", k=3)
    assert res.hits == [] and res.empty_message == r.EMPTY_MESSAGE


def test_hash_embedder_enables_the_semantic_arm_and_rrf() -> None:
    sel = r.Selector(PATTERNS, embedder=r.HashEmbedder())
    res = sel.select("route requests by content to a handler", k=3)
    assert res.retrieval_path == "rrf"
    assert res.hits[0].id == "content-routing"
    assert res.hits[0].score_semantic is not None
    assert res.hits[0].retrieval_path in ("rrf", "bm25", "semantic")


def test_relations_are_attached_one_hop() -> None:
    p = _p("x", "routes by rule", relations=[Relation(type="alternative_to", target="content-routing")])
    res = r.Selector([*PATTERNS, p], embedder=None).select("routes by rule", k=1)
    assert res.hits[0].relations == [{"type": "alternative_to", "target": "content-routing", "prefer_when": None}]


def test_result_to_dict_has_every_envelope_field() -> None:
    d = r.Selector(PATTERNS, embedder=None).select("requests", k=1).to_dict()
    assert set(d) == {"hits", "retrieval_path", "catalog_version", "auth", "empty_message"}
    assert d["auth"] == {"subject": "stdio-local"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_retrieval.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.retrieval'`

- [ ] **Step 3: Implement retrieval**

`src/agentic_patterns_catalog/retrieval.py`:
```python
"""`select`: facet filter → BM25 ∥ local embeddings → Reciprocal Rank Fusion. Deterministic; no network."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from rank_bm25 import BM25Okapi

from .cli import register
from .model import Pattern
from .paths import CATALOG_DIR
from .store import FileStore, Store, catalog_version

EMPTY_MESSAGE = "No pattern matches in the catalog."
K_RRF = 60
_TOKEN = re.compile(r"[a-z0-9]+")
Arms = Sequence[str]


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def pattern_text(p: Pattern) -> str:
    """The text both arms index: name, tldr, problem signals, use cases, and 'when to use' details."""
    d = p.content.details
    parts = [p.name, p.content.tldr.what, p.content.tldr.when, *p.selection.problem_signals, *p.content.useCases,
             *d.get("when_to_use.use_when", []), *d.get("best_use_cases", []), *d.get("top_use_cases", [])]
    return " ".join(parts)


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _normalize(v: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return v / norms


class HashEmbedder:
    """Deterministic bag-of-words hashing. For tests and as an offline stand-in; not a semantic model."""
    name = "hash-bow-256"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for row, text in enumerate(texts):
            for tok in tokenize(text):
                out[row, int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        return _normalize(out)


class FastEmbedEmbedder:
    """Local ONNX embeddings via fastembed (extra `embed`)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding  # imported here so the core install stays light

        self.name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        return _normalize(np.asarray(list(self._model.embed(texts)), dtype="float32"))


def default_embedder() -> Embedder | None:
    try:
        return FastEmbedEmbedder()
    except ImportError:
        return None


def rrf(rankings: list[list[str]], k: int = K_RRF) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion. Ties break by id so the order is reproducible."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, id in enumerate(ranking, start=1):
            scores[id] = scores.get(id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


@dataclass
class Hit:
    id: str
    name: str
    category: str
    score_bm25: float | None
    score_semantic: float | None
    rrf_rank: int
    retrieval_path: str
    reviewed: bool
    provenance: dict[str, Any]
    relations: list[dict[str, Any]]


@dataclass
class SelectResult:
    hits: list[Hit]
    retrieval_path: str
    catalog_version: str
    auth: dict[str, str]
    empty_message: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _matches(p: Pattern, facets: dict[str, str] | None) -> bool:
    return not facets or all(getattr(p.selection.facets, k, None) == v for k, v in facets.items())


class Selector:
    def __init__(self, patterns: list[Pattern], embedder: Embedder | None = None,
                 arms: Arms = ("bm25", "semantic"), version: str | None = None) -> None:
        self.patterns = sorted(patterns, key=lambda p: p.id)
        self.arms = tuple(a for a in arms if a != "semantic" or embedder is not None)
        self.embedder = embedder if "semantic" in self.arms else None
        self.version = version or catalog_version()
        texts = [pattern_text(p) for p in self.patterns]
        self._bm25 = BM25Okapi([tokenize(t) or ["_"] for t in texts]) if "bm25" in self.arms else None
        self._vectors = self.embedder.embed(texts) if self.embedder else None

    @classmethod
    def from_store(cls, store: Store, embedder: Embedder | None = None, arms: Arms = ("bm25", "semantic")) -> Selector:
        return cls(store.all(), embedder, arms)

    def select(self, task: str, facets: dict[str, str] | None = None, k: int = 5,
               subject: str = "stdio-local") -> SelectResult:
        idx = [i for i, p in enumerate(self.patterns) if _matches(p, facets)]
        path = "rrf" if len(self.arms) == 2 else (self.arms[0] if self.arms else "none")
        auth = {"subject": subject}
        if not idx:
            return SelectResult([], path, self.version, auth, EMPTY_MESSAGE)
        bm_scores: dict[str, float] = {}
        sem_scores: dict[str, float] = {}
        rankings: list[list[str]] = []
        if self._bm25 is not None:
            raw = self._bm25.get_scores(tokenize(task))
            bm_scores = {self.patterns[i].id: float(raw[i]) for i in idx if raw[i] > 0}
            rankings.append(sorted(bm_scores, key=lambda id: (-bm_scores[id], id)))
        if self._vectors is not None and self.embedder is not None:
            q = self.embedder.embed([task])[0]
            sims = self._vectors @ q
            sem_scores = {self.patterns[i].id: float(sims[i]) for i in idx}
            rankings.append(sorted(sem_scores, key=lambda id: (-sem_scores[id], id)))
        fused = rrf([r for r in rankings if r])
        if not fused:
            return SelectResult([], path, self.version, auth, EMPTY_MESSAGE)
        by_id = {p.id: p for p in self.patterns}
        hits = []
        for rank, (id, _) in enumerate(fused[:k], start=1):
            p = by_id[id]
            in_bm, in_sem = id in bm_scores, id in sem_scores
            hits.append(Hit(
                id=p.id, name=p.name, category=p.category,
                score_bm25=bm_scores.get(id), score_semantic=sem_scores.get(id), rrf_rank=rank,
                retrieval_path="rrf" if in_bm and in_sem else ("bm25" if in_bm else "semantic"),
                reviewed=p.reviewed, provenance=p.provenance.model_dump(mode="json"),
                relations=[r.model_dump(mode="json") for r in p.selection.relations],
            ))
        return SelectResult(hits, path, self.version, auth, None)


@register("select", "pick the patterns that fit a task")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("task")
    parser.add_argument("--facet", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--no-embed", action="store_true", help="BM25 only")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)

    def run(ns: argparse.Namespace) -> int:
        facets = dict(f.split("=", 1) for f in ns.facet)
        embedder = None if ns.no_embed else default_embedder()
        res = Selector.from_store(FileStore(ns.root), embedder).select(ns.task, facets or None, ns.k)
        if ns.json:
            print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
        elif res.empty_message:
            print(res.empty_message)
        else:
            for h in res.hits:
                print(f"{h.rrf_rank}. {h.id} [{h.category}] via {h.retrieval_path}"
                      f"  bm25={h.score_bm25 and round(h.score_bm25, 3)} sem={h.score_semantic and round(h.score_semantic, 3)}"
                      f"  reviewed={h.reviewed}")
            print(f"catalog {res.catalog_version}; path {res.retrieval_path}")
        return 0
    return run

```

Add to `commands.py`: `from . import retrieval  # noqa: F401`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_retrieval.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Spike — does fastembed install on Python 3.14?**

Run: `uv sync --extra dev --extra lint --extra embed && uv run python -c "from agentic_patterns_catalog.retrieval import FastEmbedEmbedder as F; e=F(); print(e.name, e.embed(['hello']).shape)"`
Expected: `BAAI/bge-small-en-v1.5 (1, 384)` after a one-time model download.
If the install fails (no `onnxruntime` wheel for 3.14): record the exact error in `docs/adr/0002-embedding-runtime.md` (Status: Proposed) with the fallback chosen — `sentence-transformers` if it installs, else keep `HashEmbedder` as the semantic arm and say so in the README — and open the question to the user. Do not silently continue with the hash embedder.

- [ ] **Step 6: Try it on the real catalog; commit**

Run: `uv run catalog select "route incoming customer requests to the right specialised agent" -k 5`
Expected: content-based or rule-based routing patterns near the top; the last line prints the catalog version and `path rrf` (or `path bm25` with `--no-embed`).

```bash
uv run --extra lint ruff check . && git add -A
git commit -m "Add hybrid select: facets, BM25, local embeddings, RRF"
```

---

### Task 11: Golden set and `catalog eval`

**Files:**
- Create: `eval/tasks.jsonl`, `eval/thresholds.json`, `src/agentic_patterns_catalog/evaluate.py`, `tests/test_evaluate.py`, `docs/data/eval.json` (generated, committed)
- Modify: `src/agentic_patterns_catalog/commands.py`

**Interfaces:**
- Consumes: `retrieval.Selector`, `retrieval.default_embedder`, `store.FileStore`.
- Produces: `evaluate.load_tasks(path) -> list[dict]`; `evaluate.run_eval(store, tasks, embedder, k=5) -> dict` shaped `{"run": {"catalog_version", "embed_model", "date", "k", "cases": n}, "arms": {"bm25": {...}, "semantic": {...} | None, "rrf": {...}}}` where each arm has `{"hit_at_k": float, "mrr": float, "cases": [{"id", "expected_ids", "top": [...], "hit": bool, "reciprocal_rank": float}]}`; `evaluate.write_eval(...) -> Path`; `evaluate.check_thresholds(report, thresholds) -> list[str]`; subcommand `catalog eval [--k N] [--no-embed]`.
- Task line shape: `{"id": "t01", "task": "…", "expected_ids": ["content-based-routing"], "expected_path": "rrf", "notes": "…"}`.

- [ ] **Step 1: Write the golden set (30 cases)**

`eval/tasks.jsonl` — 30 lines. Author them against the real catalog ids (`ls catalog/patterns/*/`). Use these first ten as written and add twenty more in the same shape, at least five each drawn from the biomedical-analysis and drone-flight-plan use cases (spec §9); every `expected_ids` entry must exist:
```jsonl
{"id": "t01", "task": "Incoming support requests span billing, legal and technical topics; send each to the right specialist agent without hand-written rules.", "expected_ids": ["content-based-routing", "llm-based-routing", "embedding-based-routing"], "expected_path": "rrf", "notes": "routing"}
{"id": "t02", "task": "Spread identical inference requests across a pool of identical workers.", "expected_ids": ["load-balancing"], "expected_path": "rrf", "notes": "routing"}
{"id": "t03", "task": "The model should critique its own draft answer and revise it before replying.", "expected_ids": ["self-critique", "reflection"], "expected_path": "rrf", "notes": "reflection; adjust ids to the catalog"}
{"id": "t04", "task": "An agent can reach thousands of tools; loading every schema into the prompt is too expensive.", "expected_ids": ["tool-retrieval"], "expected_path": "rrf", "notes": "tool-use, pack record"}
{"id": "t05", "task": "Call external APIs with typed arguments and get structured results back.", "expected_ids": ["function-calling", "structured-outputs"], "expected_path": "rrf", "notes": "tool-use"}
{"id": "t06", "task": "Run several independent research sub-tasks at the same time and merge the results.", "expected_ids": ["fan-out-fan-in", "parallel-processing"], "expected_path": "rrf", "notes": "parallelization; adjust ids"}
{"id": "t07", "task": "Generate many hypotheses, have them debate and get ranked in a tournament, then evolve the best ones.", "expected_ids": ["multi-agent-debate", "tournament-ranking"], "expected_path": "rrf", "notes": "co-scientist; adjust ids"}
{"id": "t08", "task": "Keep a long-running agent's memory within a token budget by summarising old turns.", "expected_ids": ["context-compression", "sliding-window-memory"], "expected_path": "rrf", "notes": "memory; adjust ids"}
{"id": "t09", "task": "Validate a generated flight plan against altitude ceilings and geofence rules before a human signs off.", "expected_ids": ["human-in-the-loop", "constraint-validation"], "expected_path": "rrf", "notes": "drone; adjust ids"}
{"id": "t10", "task": "Prevent a prompt-injected tool result from making the agent exfiltrate data.", "expected_ids": ["prompt-injection-defense", "tool-output-sanitization"], "expected_path": "rrf", "notes": "security; adjust ids"}
```
Where a note says "adjust ids", replace the placeholders with the real ids after reading the category directory; a case whose expected pattern is genuinely absent is a **coverage gap** — keep it, set `"expected_ids": []`, and add `"gap": true`; `run_eval` counts gap cases separately and excludes them from hit rate.

`eval/thresholds.json`:
```json
{"rrf_hit_at_k": 0.6, "bm25_hit_at_k": 0.4}
```
(Low on purpose before enrichment exists. Plan E raises them once `problem_signals` land; the numbers are published in `eval.json`, never in prose.)

- [ ] **Step 2: Write the failing tests**

`tests/test_evaluate.py`:
```python
import json
from pathlib import Path

import pytest

from agentic_patterns_catalog import evaluate, retrieval, store
from agentic_patterns_catalog.model import Content, Pattern, Provenance, Source, Tldr, content_hash


def _p(id: str, what: str) -> Pattern:
    c = Content(description=what, tldr=Tldr(what=what, when="", watchOut="w"))
    return Pattern(id=id, name=id, category="routing", complexity="low", content=c,
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


class _Mem:
    def __init__(self, ps): self._ps = ps
    def all(self): return self._ps
    def get(self, id): return next(p for p in self._ps if p.id == id)
    def put(self, p): pass
    def categories(self): return []
    def recipes(self): return []


TASKS = [
    {"id": "a", "task": "route by content", "expected_ids": ["content-routing"], "expected_path": "rrf"},
    {"id": "b", "task": "balance load across workers", "expected_ids": ["load-balancing"], "expected_path": "rrf"},
    {"id": "c", "task": "something absent", "expected_ids": [], "expected_path": "rrf", "gap": True},
]
STORE = _Mem([_p("content-routing", "routes requests by content"), _p("load-balancing", "balances load across workers")])


def test_run_eval_scores_each_arm_and_skips_gaps() -> None:
    rep = evaluate.run_eval(STORE, TASKS, retrieval.HashEmbedder(), k=2)
    assert set(rep["arms"]) == {"bm25", "semantic", "rrf"}
    assert rep["arms"]["rrf"]["hit_at_k"] == 1.0 and rep["arms"]["rrf"]["mrr"] == 1.0
    assert rep["run"]["cases"] == 2 and rep["run"]["gaps"] == 1
    assert rep["run"]["embed_model"] == "hash-bow-256"


def test_semantic_arm_is_null_without_an_embedder() -> None:
    rep = evaluate.run_eval(STORE, TASKS, None, k=2)
    assert rep["arms"]["semantic"] is None and rep["arms"]["rrf"]["hit_at_k"] == 1.0


def test_thresholds_report_shortfalls() -> None:
    rep = evaluate.run_eval(STORE, TASKS, None, k=2)
    assert evaluate.check_thresholds(rep, {"rrf_hit_at_k": 0.5}) == []
    assert evaluate.check_thresholds(rep, {"rrf_hit_at_k": 1.5}) == ["rrf_hit_at_k 1.000 < 1.500"]


def test_write_eval_and_load_tasks_roundtrip(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text("\n".join(json.dumps(t) for t in TASKS) + "\n")
    assert [t["id"] for t in evaluate.load_tasks(tasks)] == ["a", "b", "c"]
    out = evaluate.write_eval(evaluate.run_eval(STORE, TASKS, None), tmp_path / "eval.json")
    assert json.loads(out.read_text())["run"]["k"] == 5


def test_committed_tasks_reference_existing_ids() -> None:
    ids = {p.id for p in store.FileStore().all()}
    if len(ids) < 288:
        pytest.skip("needs the full local catalog (288 records)")
    for t in evaluate.load_tasks():
        for e in t["expected_ids"]:
            assert e in ids, f"{t['id']}: unknown pattern id {e}"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_evaluate.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.evaluate'`

- [ ] **Step 4: Implement eval**

`src/agentic_patterns_catalog/evaluate.py`:
```python
"""Golden-set evaluation of `select`, one arm at a time. Writes a record; prose cites it."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from .cli import register
from .paths import CATALOG_DIR, DATA_DIR, EVAL_TASKS, EVAL_THRESHOLDS
from .retrieval import Embedder, Selector, default_embedder
from .store import FileStore, Store, catalog_version

ARMS = {"bm25": ("bm25",), "semantic": ("semantic",), "rrf": ("bm25", "semantic")}


def load_tasks(path: Path = EVAL_TASKS) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _score_arm(store: Store, tasks: list[dict[str, Any]], embedder: Embedder | None, arms: tuple[str, ...],
               k: int) -> dict[str, Any] | None:
    if arms == ("semantic",) and embedder is None:
        return None  # the rrf arm degrades to bm25; run.embed_model records that
    selector = Selector.from_store(store, embedder, arms)
    cases = []
    for t in tasks:
        top = [h.id for h in selector.select(t["task"], t.get("facets"), k).hits]
        ranks = [top.index(e) + 1 for e in t["expected_ids"] if e in top]
        rr = 1.0 / min(ranks) if ranks else 0.0
        cases.append({"id": t["id"], "expected_ids": t["expected_ids"], "top": top, "hit": bool(ranks),
                      "reciprocal_rank": rr})
    n = len(cases) or 1
    return {"hit_at_k": sum(c["hit"] for c in cases) / n, "mrr": sum(c["reciprocal_rank"] for c in cases) / n,
            "cases": cases}


def run_eval(store: Store, tasks: list[dict[str, Any]], embedder: Embedder | None, k: int = 5) -> dict[str, Any]:
    scored = [t for t in tasks if not t.get("gap")]
    return {
        "run": {"catalog_version": catalog_version(), "embed_model": embedder.name if embedder else None,
                "date": dt.date.today().isoformat(), "k": k, "cases": len(scored), "gaps": len(tasks) - len(scored)},
        "arms": {name: _score_arm(store, scored, embedder, arms, k) for name, arms in ARMS.items()},
    }


def check_thresholds(report: dict[str, Any], thresholds: dict[str, float]) -> list[str]:
    """`<arm>_<metric>` thresholds that the report does not meet."""
    problems = []
    for key, floor in thresholds.items():
        arm, metric = key.split("_", 1)
        got = (report["arms"].get(arm) or {}).get(metric)
        if got is None or got < floor:
            problems.append(f"{key} {got if got is None else f'{got:.3f}'} < {floor:.3f}")
    return problems


def write_eval(report: dict[str, Any], path: Path = DATA_DIR / "eval.json") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


@register("eval", "run the golden set through every arm and write docs/data/eval.json")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--no-embed", action="store_true")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)

    def run(ns: argparse.Namespace) -> int:
        embedder = None if ns.no_embed else default_embedder()
        report = run_eval(FileStore(ns.root), load_tasks(), embedder, ns.k)
        path = write_eval(report)
        for arm, r in report["arms"].items():
            print(f"{arm:9s} " + ("not run" if r is None else f"hit@{ns.k}={r['hit_at_k']:.3f} mrr={r['mrr']:.3f}"))
        problems = check_thresholds(report, json.loads(EVAL_THRESHOLDS.read_text(encoding="utf-8")))
        print(f"wrote {path}" + (f"; below threshold: {', '.join(problems)}" if problems else ""))
        return 1 if problems else 0
    return run
```

Add to `commands.py`: `from . import evaluate  # noqa: F401`.

- [ ] **Step 5: Run the tests, then the real eval; commit**

Run: `uv run pytest tests/test_evaluate.py -q && uv run catalog eval`
Expected: `5 passed`; three arm lines; `wrote docs/data/eval.json`. If a threshold is missed, do **not** lower it in this task — fix `expected_ids` that were guessed wrong (the note said "adjust ids"), re-run, and if the real gap remains, mark the case `"gap": true` with a reason in `notes`.

```bash
uv run --extra lint ruff check . && git add -A
git commit -m "Add golden set and three-arm eval record"
```

---

### Task 12: `catalog verify`

**Files:**
- Create: `src/agentic_patterns_catalog/verify.py`, `tests/test_verify.py`
- Modify: `src/agentic_patterns_catalog/commands.py`

**Interfaces:**
- Consumes: everything above.
- Produces (subcommand also takes `--skip NAME[,NAME]`): `verify.Check = Callable[[VerifyContext], list[str]]`; `verify.VerifyContext(root: Path, strict_vocab: bool, generated_dir: Path, schema_dir: Path, eval_path: Path, thresholds_path: Path)`; `verify.CHECKS: list[tuple[str, Check]]`; `verify.run_checks(ctx) -> dict[str, list[str]]` (name → problems); `verify.run_warnings(ctx) -> dict[str, list[str]]`; subcommand `catalog verify [--strict-vocab] [--root DIR]` exiting 1 on any problem.
- Checks (spec §11): `records` (each file validates, `id == stem`, `category == parent dir`, `content_sha256 == content_hash(content)`); `index` (index.json entries equal the files present, hashes match); `relations` (targets resolve; `precedes` acyclic); `recipes` (pattern ids resolve); `schema` (`schemas_match() == []`); `facets` (vocab; warning unless `--strict-vocab`); `compiled` (fresh compile equals committed files, budgets); `eval` (`eval.json` present, thresholds met; warning when `eval.json` is absent, error when present and short).

- [ ] **Step 1: Write the failing tests**

`tests/test_verify.py`:
```python
import json
from pathlib import Path

from agentic_patterns_catalog import compile as comp
from agentic_patterns_catalog import schema, store, verify
from agentic_patterns_catalog.model import (
    Content, Facets, Pattern, Provenance, Relation, Selection, Source, Tldr, content_hash,
)
from agentic_patterns_catalog.paths import EVAL_THRESHOLDS, VOCAB_PATH


def _p(id: str, **sel) -> Pattern:
    c = Content(description=id, tldr=Tldr(what="w", when="n", watchOut="o"))
    return Pattern(id=id, name=id, category="routing", complexity="low", content=c, selection=Selection(**sel),
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


def _ctx(tmp_path: Path, **over) -> verify.VerifyContext:
    root = tmp_path / "catalog"
    (root / "categories").mkdir(parents=True)
    (root / "recipes").mkdir()
    (root / "vocab").mkdir()
    (root / "vocab" / "facets.json").write_text(VOCAB_PATH.read_text())
    fs = store.FileStore(root)
    fs.put(_p("a"))
    fs.put(_p("b", relations=[Relation(type="precedes", target="a")]))
    store.write_index(fs, root / "index.json")
    gen = tmp_path / "gen"
    comp.write_all(fs, gen)
    sch = tmp_path / "schema"
    schema.write_schemas(sch)
    base = dict(root=root, strict_vocab=False, generated_dir=gen, schema_dir=sch,
                eval_path=tmp_path / "eval.json", thresholds_path=EVAL_THRESHOLDS)
    base.update(over)
    return verify.VerifyContext(**base)


def test_clean_tree_has_no_problems(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    assert {k: v for k, v in verify.run_checks(ctx).items() if v} == {}
    assert "eval" in verify.run_warnings(ctx)  # eval.json absent → warning, not error


def test_stale_index_and_bad_hash_are_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.root / "index.json").write_text(json.dumps({"patterns": {}, "categories": [], "recipes": []}))
    path = ctx.root / "patterns" / "routing" / "a.json"
    data = json.loads(path.read_text())
    data["provenance"]["source"]["content_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    problems = verify.run_checks(ctx)
    assert problems["index"] and problems["records"]


def test_precedes_cycle_and_unknown_target_are_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    fs = store.FileStore(ctx.root)
    fs.put(_p("a", relations=[Relation(type="precedes", target="b"), Relation(type="requires", target="zzz")]))
    problems = verify.run_checks(ctx)["relations"]
    assert any("cycle" in p for p in problems) and any("zzz" in p for p in problems)


def test_unknown_facet_is_warning_unless_strict(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    store.FileStore(ctx.root).put(_p("a", facets=Facets(scale="galaxy")))
    assert verify.run_checks(ctx)["facets"] == []
    assert verify.run_warnings(ctx)["facets"] == ["a: scale=galaxy"]
    strict = _ctx(tmp_path, strict_vocab=True)
    store.FileStore(strict.root).put(_p("a", facets=Facets(scale="galaxy")))
    assert verify.run_checks(strict)["facets"] == ["a: scale=galaxy"]


def test_stale_compiled_output_is_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.generated_dir / "CATALOG.md").write_text("edited by hand\n")
    assert verify.run_checks(ctx)["compiled"] == ["CATALOG.md differs from a fresh compile"]


def test_repo_verifies_clean() -> None:
    # Committed index.json and generated/ reflect all 288 records. A checkout without the local
    # mirror (CI) holds 11, so `index` and `compiled` are expected to differ there and are skipped.
    ctx = verify.VerifyContext.default()
    indexed = len(json.loads((ctx.root / "index.json").read_text())["patterns"])
    partial = len(store.FileStore(ctx.root).all()) < indexed
    skipped = {"index", "compiled"} if partial else set()
    problems = {k: v for k, v in verify.run_checks(ctx).items() if v and k not in skipped}
    assert problems == {}, problems
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_verify.py -q`
Expected: `ModuleNotFoundError: No module named 'agentic_patterns_catalog.verify'`

- [ ] **Step 3: Implement verify**

`src/agentic_patterns_catalog/verify.py`:
```python
"""One command that checks the whole catalog. Exit 1 on any problem; warnings do not fail."""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from . import compile as comp
from . import vocab as vocab_mod
from .cli import register
from .evaluate import check_thresholds
from .model import Pattern, content_hash
from .paths import CATALOG_DIR, DATA_DIR, EVAL_THRESHOLDS, GENERATED_DIR, SCHEMA_DIR
from .schema import schemas_match
from .store import FileStore, build_index


@dataclass
class VerifyContext:
    root: Path
    strict_vocab: bool
    generated_dir: Path
    schema_dir: Path
    eval_path: Path
    thresholds_path: Path

    @classmethod
    def default(cls, strict_vocab: bool = False) -> VerifyContext:
        return cls(CATALOG_DIR, strict_vocab, GENERATED_DIR, SCHEMA_DIR, DATA_DIR / "eval.json", EVAL_THRESHOLDS)


Check = Callable[[VerifyContext], list[str]]


def check_records(ctx: VerifyContext) -> list[str]:
    problems = []
    for path in sorted((ctx.root / "patterns").glob("*/*.json")):
        try:
            p = Pattern.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as e:
            problems.append(f"{path.name}: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}")
            continue
        if p.id != path.stem:
            problems.append(f"{path.name}: id {p.id!r} != file stem")
        if p.category != path.parent.name:
            problems.append(f"{path.name}: category {p.category!r} != directory {path.parent.name!r}")
        if p.provenance.source.content_sha256 != content_hash(p.content):
            problems.append(f"{p.id}: content_sha256 does not match content")
    return problems


def check_index(ctx: VerifyContext) -> list[str]:
    path = ctx.root / "index.json"
    if not path.exists():
        return ["index.json missing; run `catalog index`"]
    committed = json.loads(path.read_text(encoding="utf-8"))
    fresh = build_index(FileStore(ctx.root))
    problems = []
    if set(committed.get("patterns", {})) != set(fresh["patterns"]):
        problems.append("index.json pattern ids differ from files on disk")
    for id, entry in fresh["patterns"].items():
        c = committed.get("patterns", {}).get(id)
        if c and c.get("content_sha256") != entry["content_sha256"]:
            problems.append(f"index.json: stale hash for {id}")
    return problems


def _relations(ctx: VerifyContext) -> tuple[dict[str, Pattern], list[str]]:
    by_id = {p.id: p for p in FileStore(ctx.root).all()}
    problems = []
    for p in by_id.values():
        for r in p.selection.relations:
            if r.target not in by_id:
                problems.append(f"{p.id}: relation target {r.target!r} does not resolve")
    return by_id, problems


def check_relations(ctx: VerifyContext) -> list[str]:
    by_id, problems = _relations(ctx)
    graph = {p.id: [r.target for r in p.selection.relations if r.type == "precedes" and r.target in by_id]
             for p in by_id.values()}
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 1:
            problems.append("precedes cycle: " + " → ".join([*trail[trail.index(node):], node]))
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for nxt in graph.get(node, []):
            visit(nxt, [*trail, node])
        state[node] = 2

    for node in sorted(graph):
        if state.get(node) != 2:
            visit(node, [])
    return problems


def check_recipes(ctx: VerifyContext) -> list[str]:
    fs = FileStore(ctx.root)
    ids = {p.id for p in fs.all()}
    return [f"recipe {r.id}: step {s.order} names unknown pattern {s.pattern_id!r}"
            for r in fs.recipes() for s in r.steps if s.pattern_id not in ids]


def check_schema(ctx: VerifyContext) -> list[str]:
    return [f"schema/{n}.schema.json is stale; run `catalog schema`" for n in schemas_match(ctx.schema_dir)]


def facet_problems(ctx: VerifyContext) -> list[str]:
    vocab = vocab_mod.load_vocab(ctx.root / "vocab" / "facets.json")
    out = []
    for p in FileStore(ctx.root).all():
        out += [f"{p.id}: {bad}" for bad in vocab_mod.unknown_facet_values(p.selection.facets.model_dump(), vocab)]
    return out


def check_facets(ctx: VerifyContext) -> list[str]:
    return facet_problems(ctx) if ctx.strict_vocab else []


def check_compiled(ctx: VerifyContext) -> list[str]:
    outputs = comp.compile_all(FileStore(ctx.root))
    problems = [f"{n} over budget ({comp.token_estimate(outputs[n])} > {comp.BUDGETS[n]} tokens)"
                for n in comp.over_budget(outputs)]
    for rel, text in outputs.items():
        path = ctx.generated_dir / rel
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            problems.append(f"{rel} differs from a fresh compile")
    return problems


def check_eval(ctx: VerifyContext) -> list[str]:
    if not ctx.eval_path.exists():
        return []
    report = json.loads(ctx.eval_path.read_text(encoding="utf-8"))
    return check_thresholds(report, json.loads(ctx.thresholds_path.read_text(encoding="utf-8")))


CHECKS: list[tuple[str, Check]] = [
    ("records", check_records), ("index", check_index), ("relations", check_relations), ("recipes", check_recipes),
    ("schema", check_schema), ("facets", check_facets), ("compiled", check_compiled), ("eval", check_eval),
]


def run_checks(ctx: VerifyContext) -> dict[str, list[str]]:
    return {name: check(ctx) for name, check in CHECKS}


def run_warnings(ctx: VerifyContext) -> dict[str, list[str]]:
    warnings: dict[str, list[str]] = {}
    if not ctx.strict_vocab:
        bad = facet_problems(ctx)
        if bad:
            warnings["facets"] = bad
    if not ctx.eval_path.exists():
        warnings["eval"] = [f"{ctx.eval_path} absent; run `catalog eval`"]
    return warnings


@register("verify", "check records, index, relations, schema, facets, compiled views and eval")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--strict-vocab", action="store_true", help="unknown facet values fail instead of warn")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)
    parser.add_argument("--skip", default="", metavar="NAME[,NAME]",
                        help="checks to skip, e.g. index,compiled on a checkout without the 277 local records")

    def run(ns: argparse.Namespace) -> int:
        ctx = VerifyContext.default(ns.strict_vocab)
        ctx.root = ns.root
        skipped = {n for n in ns.skip.split(",") if n}
        problems = {name: items for name, items in run_checks(ctx).items() if name not in skipped}
        for name, items in problems.items():
            print(f"{'FAIL' if items else 'ok  '} {name}" + (f" ({len(items)})" if items else ""))
            for item in items[:20]:
                print(f"       {item}")
        for name, items in run_warnings(ctx).items():
            print(f"warn {name}: {items[0]}" + (f" (+{len(items) - 1} more)" if len(items) > 1 else ""))
        return 1 if any(problems.values()) else 0
    return run
```

Add to `commands.py`: `from . import verify  # noqa: F401`.

- [ ] **Step 4: Run the tests, then verify the repo**

Run: `uv run pytest tests/test_verify.py -q && uv run catalog verify`
Expected: `6 passed`; every check `ok`. If `compiled` fails, run `uv run catalog compile` and `uv run catalog index` — a record changed after the last compile.

- [ ] **Step 5: Ruff; commit**

```bash
uv run --extra lint ruff check . && git add -A
git commit -m "Add catalog verify"
```

---

### Task 13: Smoke test record, CI, README completion

**Files:**
- Create: `.github/workflows/verify.yml`, `docs/data/smoke.json`, `docs/eval-how-to.md`
- Modify: `README.md`

- [ ] **Step 1: The smoke test (spec §9) — manual, recorded**

Compile the local full index: `uv run catalog compile --local` (writes to `skills/agentic-patterns/generated/local/`, gitignored). Open a fresh Claude Code session, paste the content of `local/CATALOG-full.md` and, one at a time, the five task texts `t01`, `t04`, `t06`, `t07`, `t09` from `eval/tasks.jsonl`; ask "Which pattern ids from this list apply? Answer with ids only." Record the answers **verbatim** in `docs/data/smoke.json`:

```json
{
  "run": {"date": "YYYY-MM-DD", "catalog_version": "<git sha from `catalog verify` output>", "index": "CATALOG-full.md (local, tldr for all records)", "model": "<model id shown in the session>"},
  "cases": [
    {"id": "t01", "answered_ids": [], "expected_ids": [], "sensible": true, "note": ""}
  ]
}
```
One entry per case; `sensible` is your judgement, `note` says why when it is false. This record is what §14 step 3 calls "recorded verdicts".

- [ ] **Step 2: CI**

`.github/workflows/verify.yml`:
```yaml
name: verify
on: [push, pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --extra dev --extra lint
      - run: uv run --extra lint ruff check .
      - run: uv run pytest -q
      - run: uv run catalog verify --skip index,compiled
```
Why `--skip index,compiled`: the committed `catalog/index.json` and `skills/agentic-patterns/generated/` reflect all 288 records (ids, names, hashes — no site prose), because the skill needs the full list. CI holds only the 11 committed records, so a fresh index or compile there would legitimately differ. Those two checks run locally, where the 277 extracted records exist, and `catalog verify` with no `--skip` is the pre-commit gate. Add this line to `CLAUDE.md` under Conventions: "Committed `index.json` and `generated/` reflect all 288 records. Run `catalog index && catalog compile && catalog verify` locally before committing; CI runs `verify --skip index,compiled`."

- [ ] **Step 3: `docs/eval-how-to.md` and README**

`docs/eval-how-to.md`:
```markdown
# How to run the evaluation

`uv run catalog eval` runs `eval/tasks.jsonl` through three arms of `select` (BM25, semantic, RRF)
and writes `docs/data/eval.json`. `eval/thresholds.json` names the floors `catalog verify` enforces.
The semantic arm needs the `embed` extra: `uv sync --extra embed`.

Illustrative output (pasted from a run; nothing asserts it):

```
<paste the console output of one real run here, with the date>
```

Results are the record, not this page. Quote figures from `docs/data/eval.json`.
```

Append to `README.md` after Quick start:
```markdown
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
```

- [ ] **Step 4: Final verification and commit**

Run: `uv run pytest -q && uv run --extra lint ruff check . && uv run catalog verify`
Expected: all green.

```bash
git add -A
git commit -m "Add CI, smoke-test record and eval how-to

Docs and workflow only; the workflow runs the existing test suite."
```

---

## Self-review against the spec

- §2 properties: bare install = pydantic + rank-bm25 + bs4 (Task 1); provenance on every hit (Task 10); empty message (Task 10); generated numbers (Task 11, 13); one verify command (Task 12). ✔
- §3 inputs/licenses: pack copy + license note (Task 7); 277 gitignored (Task 1 `.gitignore` already present); both page sources parsed (Tasks 4–6). ✔
- §4.1–4.4 models, vocabulary file, index, relations DAG check: Tasks 2, 3, 8, 12. ✔
- §4.5 recipes: model + verify check present (Tasks 3, 12); the two recipe files are Plan E. ✔ (deferred, stated)
- §4.6 Store protocol + FileStore: Task 8. `embeddings()` on the store is **not** implemented here — the Selector recomputes vectors per process; an on-disk cache under `catalog/embeddings/` is left to Plan C together with `PostgresStore`, since that is where the storage decision lands. Noted as a deviation from §4.6's method list.
- §5 select envelope fields: Task 10 (`hits, retrieval_path, catalog_version, auth, empty_message`). ✔
- §7 compiled views and budgets: Task 9; budgets 2k / 16k; SKILL.md itself is Plan D. ✔
- §9 eval + smoke: Tasks 11, 13. ✔
- §11 verify checks, ruff, toolchain: Tasks 1, 12, 13. ✔
- Type consistency: `Selector.from_store(store, embedder, arms)` is used identically in Tasks 10 and 11; `content_hash`, `dumps`, `FileStore.put/all/get/categories/recipes`, `write_index`, `compile_all(store, local=)`, `check_thresholds(report, thresholds)` keep one signature throughout. ✔
- Placeholder scan: the golden set says "adjust ids" for cases 03, 06–10 — that is an explicit instruction with a rule for gaps, not a TBD. The smoke record and eval how-to say "paste from a run" by design (spec §2: pasted, never typed). ✔
