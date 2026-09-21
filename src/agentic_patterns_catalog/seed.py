"""Seed Pattern records from the free pack's patterns.json (the 11 licensed sample records)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .cli import register
from .model import Content, Pattern, Provenance, Source, Tldr, content_hash
from .paths import CATALOG_DIR, CONTENT_CACHE_DIR, PACK_JSON, SITE
from .store import FileStore


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
    """One Pattern per entry of the pack's `patterns` list, tagged `free-pack`."""
    return [_pattern(raw) for raw in pack["patterns"]]


def write_seed(pack_path: Path = PACK_JSON, out_dir: Path = CATALOG_DIR, *,
               cache_dir: Path = CONTENT_CACHE_DIR) -> int:
    """Write one record per pack entry and cache its content. Returns the count.

    A record that already exists keeps its enrichment: the pack refreshes content and source
    provenance only, the same way `extract_mirror` does.
    """
    patterns = seed_from_pack(json.loads(pack_path.read_text(encoding="utf-8")))
    store = FileStore(out_dir, cache_dir)
    for p in patterns:
        target = out_dir / "patterns" / p.category / f"{p.id}.json"
        if target.is_file():
            existing = Pattern.model_validate_json(target.read_text(encoding="utf-8"))
            provenance = p.provenance.model_copy(update={"enrichment": existing.provenance.enrichment})
            p = p.model_copy(update={"selection": existing.selection, "provenance": provenance})
        store.put(p)
    return len(patterns)


@register("seed", "write the free-pack records into the catalog")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--pack", type=Path, default=PACK_JSON)
    parser.add_argument("--out", type=Path, default=CATALOG_DIR)
    parser.add_argument("--cache", type=Path, default=CONTENT_CACHE_DIR,
                        help="where extracted site content is cached (never tracked)")

    def run(ns: argparse.Namespace) -> int:
        print(f"seeded {write_seed(ns.pack, ns.out, cache_dir=ns.cache)} records")
        return 0
    return run
