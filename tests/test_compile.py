from pathlib import Path

import pytest

from agentic_patterns_catalog import compile as comp
from agentic_patterns_catalog import store
from agentic_patterns_catalog.model import (
    Category,
    Content,
    ImplementationGuide,
    Pattern,
    Provenance,
    Relation,
    Selection,
    Source,
    Tldr,
    content_hash,
)


def _p(id: str, extraction: str = "rsc-payload", **sel) -> Pattern:
    c = Content(description=f"{id} does X.", tldr=Tldr(what=f"{id} what", when=f"{id} when", watchOut="w"),
                features=["f1"], useCases=["u1"], example="ex", code={"python": "print(1)"}, references=["r - u"])
    return Pattern(id=id, name=id.title(), category="routing", complexity="low", content=c, selection=Selection(**sel),
                   provenance=Provenance(source=Source(url="u", extraction=extraction, content_sha256=content_hash(c))))


@pytest.fixture
def fs(tmp_path: Path) -> store.FileStore:
    s = store.FileStore(tmp_path)
    s.put(_p("pack-one", "free-pack"))
    s.put(_p("plain-two"))
    s.put(_p("rich-three", problem_signals=["requests span domains"],
             relations=[Relation(type="alternative_to", target="plain-two", prefer_when="rules are known")]))
    (tmp_path / "categories").mkdir()
    cat = Category(id="routing", name="Routing", description="Dispatch.",
                   implementationGuide=ImplementationGuide(whenToUse=["many handlers"]),
                   technique_ids=["pack-one", "plain-two", "rich-three"],
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256="0" * 64)))
    (tmp_path / "categories" / "routing.json").write_text(cat.model_dump_json())
    return s


def test_catalog_md_is_one_line_per_category(fs: store.FileStore) -> None:
    out = comp.compile_all(fs)
    assert out["CATALOG.md"].strip().splitlines()[-1] == "- **routing** — Routing — 3 patterns"


def test_local_catalog_md_and_guide_carry_the_category_prose(fs: store.FileStore) -> None:
    out = comp.compile_all(fs, local=True)
    assert out["CATALOG.md"].strip().splitlines()[-1] == "- **routing** — Dispatch. — 3 patterns"
    assert "Dispatch." in out["guides/routing.md"] and "many handlers" in out["guides/routing.md"]


def test_full_index_quotes_tldr_only_for_pack_records(fs: store.FileStore) -> None:
    lines = comp.compile_all(fs)["CATALOG-full.md"].splitlines()
    assert "- pack-one — pack-one what — use when: pack-one when" in lines
    assert "- plain-two — Plain-Two" in lines
    assert "- rich-three — Rich-Three — requests span domains" in lines
    assert not any("plain-two what" in line for line in lines)


def test_local_mode_uses_tldr_for_everyone(fs: store.FileStore) -> None:
    lines = comp.compile_all(fs, local=True)["CATALOG-full.md"].splitlines()
    assert "- plain-two — plain-two what — use when: plain-two when" in lines


def test_guide_has_table_and_alternatives_and_no_category_prose(fs: store.FileStore) -> None:
    guide = comp.compile_all(fs)["guides/routing.md"]
    assert "many handlers" not in guide and "Dispatch." not in guide
    assert "| rich-three | Rich-Three | low |" in guide
    assert "rich-three → plain-two: rules are known" in guide


def test_sheets_only_for_pack_records_unless_local(fs: store.FileStore) -> None:
    assert "sheets/pack-one.md" in comp.compile_all(fs)
    assert "sheets/plain-two.md" not in comp.compile_all(fs)
    assert "sheets/plain-two.md" in comp.compile_all(fs, local=True)
    sheet = comp.compile_all(fs)["sheets/pack-one.md"]
    assert sheet.startswith("# Pack-One") and "## In 30 seconds" in sheet and "```python" in sheet


def test_budget_check_names_offenders() -> None:
    assert comp.over_budget({"CATALOG.md": "x" * 4 * 2001, "CATALOG-full.md": "y"}) == ["CATALOG.md"]
    assert comp.token_estimate("abcd" * 10) == 10


def test_write_all_creates_files(fs: store.FileStore, tmp_path: Path) -> None:
    written, removed = comp.write_all(fs, tmp_path / "gen", local=False)
    assert removed == []
    assert (tmp_path / "gen" / "CATALOG.md").exists()
    assert any(p.name == "routing.md" for p in written)


def test_compile_embeddings_writes_the_cache_under_the_catalog_root(
        fs: store.FileStore, tmp_path: Path, monkeypatch, capsys) -> None:
    from agentic_patterns_catalog import cli, retrieval
    monkeypatch.setattr(comp, "default_embedder", lambda: retrieval.HashEmbedder())
    assert cli.main(["compile", "--root", str(tmp_path), "--out", str(tmp_path / "out"), "--embeddings"]) == 0
    cache = tmp_path / "embeddings" / "hash-bow-256.npy"
    assert cache.exists() and cache.with_suffix(".json").exists()
    assert f"embeddings: {cache} (3, 256)" in capsys.readouterr().out


def test_compile_no_embeddings_writes_no_cache(fs: store.FileStore, tmp_path: Path, monkeypatch) -> None:
    from agentic_patterns_catalog import cli, retrieval
    monkeypatch.setattr(comp, "default_embedder", lambda: retrieval.HashEmbedder())
    assert cli.main(["compile", "--root", str(tmp_path), "--out", str(tmp_path / "out"), "--no-embeddings"]) == 0
    assert not (tmp_path / "embeddings").exists()
