import json
from pathlib import Path

import pytest

from agentic_patterns_catalog import store
from agentic_patterns_catalog.model import Content, Pattern, Provenance, Source, Tldr, content_hash


def _p(id: str, category: str = "routing") -> Pattern:
    c = Content(description=f"{id} d", tldr=Tldr(what="w", when="n", watchOut="o"))
    return Pattern(id=id, name=id.title(), category=category, complexity="low", content=c,
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


@pytest.fixture
def fs(tmp_path: Path) -> store.FileStore:
    s = store.FileStore(tmp_path)
    for p in (_p("b-pat"), _p("a-pat"), _p("c-pat", "memory-management")):
        s.put(p)
    return s


def test_put_writes_under_category_and_all_is_sorted_by_id(fs: store.FileStore, tmp_path: Path) -> None:
    assert (tmp_path / "patterns" / "routing" / "a-pat.json").exists()
    assert [p.id for p in fs.all()] == ["a-pat", "b-pat", "c-pat"]


def test_get_unknown_id_raises_key_error(fs: store.FileStore) -> None:
    with pytest.raises(KeyError):
        fs.get("nope")
    assert fs.get("a-pat").category == "routing"
    assert fs.get("c-pat").category == "memory-management"


def test_get_does_not_glob_or_leave_the_patterns_tree(fs: store.FileStore) -> None:
    for id in ("*", "*-pat", "../routing/a-pat", "routing/a-pat"):
        with pytest.raises(KeyError):
            fs.get(id)


def test_index_lists_every_pattern_with_hash_and_review_state(fs: store.FileStore, tmp_path: Path) -> None:
    idx = store.write_index(fs, tmp_path / "index.json")
    assert set(idx["patterns"]) == {"a-pat", "b-pat", "c-pat"}
    assert idx["patterns"]["a-pat"]["reviewed"] is False
    assert idx["patterns"]["a-pat"]["extraction"] == "rsc-payload"
    assert json.loads((tmp_path / "index.json").read_text())["patterns"]["c-pat"]["category"] == "memory-management"


def test_catalog_version_is_a_short_string() -> None:
    v = store.catalog_version()
    assert isinstance(v, str) and 4 <= len(v) <= 20
