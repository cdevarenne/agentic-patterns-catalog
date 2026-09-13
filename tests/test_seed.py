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
