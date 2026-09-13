import json
from pathlib import Path

from agentic_patterns_catalog import schema, vocab
from agentic_patterns_catalog.paths import SCHEMA_DIR


def test_generated_schema_embeds_the_vocabulary() -> None:
    s = schema.generate_schemas(vocab.load_vocab())["pattern"]
    scale = s["$defs"]["Facets"]["properties"]["scale"]
    assert {"type": "string", "enum": ["single-agent", "multi-agent", "fleet"]} in scale["anyOf"]
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_committed_schemas_equal_generated() -> None:
    assert schema.schemas_match(SCHEMA_DIR) == []


def test_write_then_match_roundtrip(tmp_path: Path) -> None:
    schema.write_schemas(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "category.schema.json", "pattern.schema.json", "recipe.schema.json",
    ]
    assert schema.schemas_match(tmp_path) == []
    (tmp_path / "recipe.schema.json").write_text(json.dumps({"changed": True}))
    assert schema.schemas_match(tmp_path) == ["recipe"]
