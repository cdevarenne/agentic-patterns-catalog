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
