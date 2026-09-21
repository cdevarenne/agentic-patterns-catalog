"""Repository-relative paths. `CATALOG_ROOT` overrides the in-tree default (ADR-0004)."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """`$CATALOG_ROOT` when set, else the checkout this package lives in. The override must hold `catalog/`."""
    override = os.environ.get("CATALOG_ROOT")
    if not override:
        return Path(__file__).resolve().parents[2]
    root = Path(override).expanduser().resolve()
    if not (root / "catalog").is_dir():
        raise FileNotFoundError(f"CATALOG_ROOT={override!r} has no catalog/ directory")
    return root


ROOT = repo_root()
CATALOG_DIR = ROOT / "catalog"
PATTERNS_DIR = CATALOG_DIR / "patterns"
CATEGORIES_DIR = CATALOG_DIR / "categories"
RECIPES_DIR = CATALOG_DIR / "recipes"
VOCAB_PATH = CATALOG_DIR / "vocab" / "facets.json"
INDEX_PATH = CATALOG_DIR / "index.json"
EMBEDDINGS_DIR = CATALOG_DIR / "embeddings"
# Site content is a rebuildable cache, never tracked (ADR-0003). `var/` is gitignored.
CONTENT_CACHE_DIR = ROOT / "var" / "content"
SCHEMA_DIR = ROOT / "schema"
DATA_DIR = ROOT / "docs" / "data"
GENERATED_DIR = ROOT / "skills" / "agentic-patterns" / "generated"
EVAL_TASKS = ROOT / "eval" / "tasks.jsonl"
EVAL_THRESHOLDS = ROOT / "eval" / "thresholds.json"
EVAL_GATE = ROOT / "eval" / "gate.json"
PACK_JSON = ROOT / "data" / "pack" / "patterns.json"
SITE = "https://agentic-design.ai"
