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
    Category,
    Content,
    Flow,
    ImplementationGuide,
    Pattern,
    Provenance,
    Source,
    Tldr,
    content_hash,
    dumps,
)
from .paths import CATALOG_DIR, CONTENT_CACHE_DIR, SITE
from .rsc import page_props
from .store import FileStore


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
        technique_ids=[t if isinstance(t, str) else t["id"]
                       for t in raw.get("techniques") or [] if isinstance(t, str) or "id" in t],
        provenance=Provenance(source=Source(
            url=f"{SITE}/patterns/{raw['id']}", mirrored_at=mirrored_at, extraction="rsc-payload",
            content_sha256=hashlib.sha256(payload).hexdigest())),
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


def extract_mirror(mirror_dir: Path, out_dir: Path = CATALOG_DIR, *,
                   cache_dir: Path = CONTENT_CACHE_DIR, force: bool = False) -> ExtractReport:
    """Every `<category>/<slug>.html` under `mirror_dir` becomes a record, a cached content file
    and a category record. A record's selection and its provenance are read back and kept."""
    report = ExtractReport()
    categories: dict[str, Category] = {}
    store = FileStore(out_dir, cache_dir)
    for page in sorted(mirror_dir.glob("*/*.html")):
        mirrored_at = dt.datetime.fromtimestamp(page.stat().st_mtime, dt.UTC).date().isoformat()
        url = f"{SITE}/patterns/{page.parent.name}/{page.stem}"
        try:
            pattern, cats = extract_page(page.read_text(encoding="utf-8"), url=url, mirrored_at=mirrored_at)
        except (ValueError, KeyError) as e:
            raise ValueError(f"{page}: {e}") from e
        for c in cats:
            categories.setdefault(c.id, c)
        target = out_dir / "patterns" / pattern.category / f"{pattern.id}.json"
        if _is_pack_record(target) and not force:
            report.skipped_pack += 1
            continue
        if not pattern.content.details:
            report.empty_details.append(pattern.id)
        if target.is_file():
            # The record on disk owns the enrichment: its selection and that selection's provenance.
            # Extraction refreshes content and source provenance only.
            existing = Pattern.model_validate_json(target.read_text(encoding="utf-8"))
            provenance = pattern.provenance.model_copy(update={"enrichment": existing.provenance.enrichment})
            pattern = pattern.model_copy(update={"selection": existing.selection, "provenance": provenance})
        store.put(pattern)
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
    parser.add_argument("--cache", type=Path, default=CONTENT_CACHE_DIR,
                        help="where extracted site content is cached (never tracked)")
    parser.add_argument("--force", action="store_true", help="overwrite records seeded from the free pack")

    def run(ns: argparse.Namespace) -> int:
        r = extract_mirror(ns.mirror, ns.out, cache_dir=ns.cache, force=ns.force)
        print(f"written {r.written}, skipped pack records {r.skipped_pack}, categories {r.categories}, "
              f"empty details {len(r.empty_details)}")
        return 0
    return run
