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
    # 92 of 288 real pages ship a lighter template: a plain `overviewFallback` summary instead of
    # the sectioned hidden-details block. parse_details() correctly returns {} for those (verified:
    # their raw HTML has no "Core Mechanism" / "Key Features" / "KPI" / "Common Pitfalls" text at all).
    assert len(report.empty_details) < 100, report.empty_details
