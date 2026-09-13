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
