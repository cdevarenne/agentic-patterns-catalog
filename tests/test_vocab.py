import json
from pathlib import Path

import pytest

from agentic_patterns_catalog import vocab


def test_committed_vocab_has_every_facet_with_unique_values() -> None:
    v = vocab.load_vocab()
    assert set(v) == set(vocab.FACET_NAMES)
    for name, values in v.items():
        assert values, name
        assert len(values) == len(set(values)), name


def test_initial_values_match_the_spec() -> None:
    v = vocab.load_vocab()
    assert v["scale"] == ["single-agent", "multi-agent", "fleet"]
    assert v["maturity"] == ["research", "emerging", "production"]


def test_missing_facet_is_an_error(tmp_path: Path) -> None:
    p = tmp_path / "facets.json"
    p.write_text(json.dumps({"scale": ["x"]}))
    with pytest.raises(ValueError, match="lacks"):
        vocab.load_vocab(p)


def test_unknown_values_are_reported_by_facet() -> None:
    v = vocab.load_vocab()
    bad = vocab.unknown_facet_values({"scale": "galaxy", "maturity": "production", "token_cost": None}, v)
    assert bad == ["scale=galaxy"]
