import json
from pathlib import Path

import pytest

from agentic_patterns_catalog import extract, store
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
    existing.write_text(json.dumps({
        "id": "fixture-routing", "name": "Fixture Routing", "category": "routing", "complexity": "low",
        "provenance": {"source": {"url": "https://example.com", "extraction": "free-pack",
                                   "content_sha256": "0" * 64}},
    }))

    cache = tmp_path / "cache"
    report = extract.extract_mirror(tmp_path / "mirror", out, cache_dir=cache)
    assert report.skipped_pack == 1 and report.written == 0 and report.categories == 1
    assert json.loads(existing.read_text())["provenance"]["source"]["extraction"] == "free-pack"

    report = extract.extract_mirror(tmp_path / "mirror", out, cache_dir=cache, force=True)
    assert report.written == 1
    Pattern.model_validate_json(existing.read_text())
    assert (out / "categories" / "routing.json").exists()


def test_malformed_page_error_names_the_file(tmp_path: Path) -> None:
    bad = tmp_path / "mirror" / "routing" / "broken.html"
    bad.parent.mkdir(parents=True)
    bad.write_text("<html><script>self.__next_f.push([1,\"1:[]\\n\"])</script></html>")
    with pytest.raises(ValueError, match="broken.html"):
        extract.extract_mirror(tmp_path / "mirror", tmp_path / "catalog", cache_dir=tmp_path / "cache")


def test_page_with_incomplete_tldr_error_names_the_file(fixtures: Path, tmp_path: Path) -> None:
    html = (fixtures / "page.html").read_text(encoding="utf-8")
    cut = ',\\"watchOut\\":\\"Stale capability data.\\"'
    assert cut in html
    bad = tmp_path / "mirror" / "routing" / "no-watchout.html"
    bad.parent.mkdir(parents=True)
    bad.write_text(html.replace(cut, ""), encoding="utf-8")
    with pytest.raises(ValueError, match="no-watchout.html.*watchOut"):
        extract.extract_mirror(tmp_path / "mirror", tmp_path / "catalog", cache_dir=tmp_path / "cache")


def test_re_extracting_preserves_enrichment(fixtures: Path, tmp_path: Path) -> None:
    mirror = tmp_path / "mirror" / "routing"
    mirror.mkdir(parents=True)
    (mirror / "fixture-routing.html").write_text((fixtures / "page.html").read_text(encoding="utf-8"))
    out, cache = tmp_path / "catalog", tmp_path / "cache"
    extract.extract_mirror(tmp_path / "mirror", out, cache_dir=cache)

    fs = store.FileStore(out, cache)
    enriched = fs.get("fixture-routing")
    enriched.selection.problem_signals = ["requests span several domains"]
    enriched.selection.facets.scale = "multi-agent"
    fs.put(enriched)

    extract.extract_mirror(tmp_path / "mirror", out, cache_dir=cache)
    after = fs.get("fixture-routing")
    assert after.selection.problem_signals == ["requests span several domains"]
    assert after.selection.facets.scale == "multi-agent"
    assert after.content is not None and after.content.tldr.what.startswith("Matches")


def test_extract_writes_no_prose_into_the_tracked_record(fixtures: Path, tmp_path: Path) -> None:
    mirror = tmp_path / "mirror" / "routing"
    mirror.mkdir(parents=True)
    (mirror / "fixture-routing.html").write_text((fixtures / "page.html").read_text(encoding="utf-8"))
    out, cache = tmp_path / "catalog", tmp_path / "cache"
    extract.extract_mirror(tmp_path / "mirror", out, cache_dir=cache)
    record = (out / "patterns" / "routing" / "fixture-routing.json").read_text()
    assert "Matches" not in record
    assert (cache / "routing" / "fixture-routing.json").is_file()


@pytest.mark.mirror
def test_real_mirror_extracts_288_patterns_and_24_categories(mirror: Path, tmp_path: Path) -> None:
    report = extract.extract_mirror(mirror, tmp_path / "catalog", cache_dir=tmp_path / "cache")
    assert report.written == 288 and report.categories == 24
    # 92 of 288 real pages ship a lighter template: a plain `overviewFallback` summary instead of
    # the sectioned hidden-details block. parse_details() correctly returns {} for those (verified:
    # their raw HTML has no "Core Mechanism" / "Key Features" / "KPI" / "Common Pitfalls" text at all).
    assert len(report.empty_details) < 100, report.empty_details
