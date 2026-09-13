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
