import json
from pathlib import Path

from agentic_patterns_catalog import seed
from agentic_patterns_catalog.model import Enrichment, Pattern
from agentic_patterns_catalog.paths import PACK_JSON, PATTERNS_DIR
from agentic_patterns_catalog.store import FileStore


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
    cache = tmp_path / "cache"
    n = seed.write_seed(fixtures / "pack.json", tmp_path, cache_dir=cache)
    assert n == 2
    files = sorted((tmp_path / "patterns" / "tool-use").glob("*.json"))
    assert len(files) == 2
    assert not any('"content"' in p.read_text() for p in files)
    Pattern.model_validate_json(files[0].read_text(encoding="utf-8"))


def test_committed_tool_use_records_match_the_pack() -> None:
    pack = json.loads(PACK_JSON.read_text(encoding="utf-8"))
    committed = {p.stem for p in (PATTERNS_DIR / "tool-use").glob("*.json")}
    assert committed == {p["id"] for p in pack["patterns"]}
    for path in (PATTERNS_DIR / "tool-use").glob("*.json"):
        assert Pattern.model_validate_json(path.read_text(encoding="utf-8")).provenance.source.extraction == "free-pack"


def test_seed_writes_records_and_fills_the_content_cache(fixtures: Path, tmp_path: Path) -> None:
    out, cache = tmp_path / "catalog", tmp_path / "cache"
    assert seed.write_seed(fixtures / "pack.json", out, cache_dir=cache) == 2
    record = next((out / "patterns" / "tool-use").glob("*.json")).read_text()
    assert '"content"' not in record
    cached = sorted((cache / "tool-use").glob("*.json"))
    assert len(cached) == 2
    assert "tldr" in json.loads(cached[0].read_text())


def test_write_seed_keeps_enrichment_and_refreshes_content(fixtures: Path, tmp_path: Path) -> None:
    out, cache = tmp_path / "catalog", tmp_path / "cache"
    seed.write_seed(fixtures / "pack.json", out, cache_dir=cache)
    fs = FileStore(out, cache)
    id = seed.seed_from_pack(json.loads((fixtures / "pack.json").read_text(encoding="utf-8")))[0].id
    p = fs.get(id)
    p.selection.problem_signals = ["needs an external tool"]
    p.selection.facets.scale = "multi-agent"
    p.provenance.enrichment["problem_signals"] = Enrichment(method="human", date="2026-09-20", reviewed_by="cdevarenne")
    p.content.description = "edited by hand; the pack must win"
    fs.put(p)
    seed.write_seed(fixtures / "pack.json", out, cache_dir=cache)
    again = fs.get(id)
    assert again.selection.problem_signals == ["needs an external tool"]
    assert again.selection.facets.scale == "multi-agent"
    assert again.provenance.enrichment["problem_signals"].reviewed_by == "cdevarenne"
    assert again.provenance.source.extraction == "free-pack"
    assert again.content.description != "edited by hand; the pack must win"
