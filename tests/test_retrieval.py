import json
from pathlib import Path

import numpy as np
import pytest

from agentic_patterns_catalog import retrieval as r
from agentic_patterns_catalog.model import (
    Content,
    Facets,
    Pattern,
    Provenance,
    Relation,
    Selection,
    Source,
    Tldr,
    content_hash,
)
from agentic_patterns_catalog.store import content_version


def _p(id: str, what: str, when: str = "", **sel) -> Pattern:
    c = Content(description=what, tldr=Tldr(what=what, when=when, watchOut="w"))
    return Pattern(id=id, name=id, category="routing", complexity="low", content=c, selection=Selection(**sel),
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


PATTERNS = [
    _p("content-routing", "Classifies request content and routes to a specialised handler.",
       "requests span several domains", facets=Facets(scale="multi-agent")),
    _p("load-balancing", "Spreads requests evenly across identical workers.", "workers are identical",
       facets=Facets(scale="fleet")),
    _p("reflection", "Model critiques and revises its own draft.", "quality matters more than latency"),
]


def test_tokenize_and_pattern_text() -> None:
    assert r.tokenize("Route, requests: by-intent!") == ["route", "requests", "by", "intent"]
    assert "requests span several domains" in r.pattern_text(PATTERNS[0])


def test_pattern_text_works_without_content() -> None:
    p = _p("x", "unused").model_copy(update={"content": None})
    p.selection.problem_signals = ["requests span several domains"]
    text = r.pattern_text(p)
    assert "requests span several domains" in text and "x" in text
    res = r.Selector([*PATTERNS, p], embedder=None, gate=r.GATE_OFF).select("requests span several domains", k=1)
    assert res.hits[0].id == "x"


def test_rrf_prefers_ids_present_in_both_lists() -> None:
    fused = r.rrf([["a", "b", "c"], ["b", "a"]], k=60)
    assert [i for i, _ in fused][:2] == ["a", "b"] or [i for i, _ in fused][:2] == ["b", "a"]
    assert fused[0][1] > fused[2][1]
    assert r.rrf([["x"], ["x"]])[0][1] == pytest.approx(2 / 61)


def test_bm25_only_select_is_deterministic_and_carries_provenance() -> None:
    sel = r.Selector(PATTERNS, embedder=None, gate=r.GATE_OFF)
    res = sel.select("route requests by content to a handler", k=2)
    assert res.retrieval_path == "bm25"
    assert res.hits[0].id == "content-routing"
    assert res.hits[0].score_semantic is None and res.hits[0].retrieval_path == "bm25"
    assert res.hits[0].provenance["source"]["extraction"] == "rsc-payload"
    assert res.empty_message is None
    assert res.hits == sel.select("route requests by content to a handler", k=2).hits


def test_facet_filter_restricts_candidates() -> None:
    sel = r.Selector(PATTERNS, embedder=None, gate=r.GATE_OFF)
    res = sel.select("requests", facets={"scale": "fleet"}, k=5)
    assert [h.id for h in res.hits] == ["load-balancing"]


def test_no_lexical_overlap_gives_the_empty_message() -> None:
    res = r.Selector(PATTERNS, embedder=None, gate=r.GATE_OFF).select("photosynthesis", k=3)
    assert res.hits == [] and res.empty_message == r.EMPTY_MESSAGE


def test_hash_embedder_enables_the_semantic_arm_and_rrf() -> None:
    sel = r.Selector(PATTERNS, embedder=r.HashEmbedder(), gate=r.GATE_OFF)
    res = sel.select("route requests by content to a handler", k=3)
    assert res.retrieval_path == "rrf"
    assert res.hits[0].id == "content-routing"
    assert res.hits[0].score_semantic is not None
    assert res.hits[0].retrieval_path in ("rrf", "bm25", "semantic")


def test_relations_are_attached_one_hop() -> None:
    p = _p("x", "routes by rule", relations=[Relation(type="alternative_to", target="content-routing")])
    res = r.Selector([*PATTERNS, p], embedder=None, gate=r.GATE_OFF).select("routes by rule", k=1)
    assert res.hits[0].relations == [{"type": "alternative_to", "target": "content-routing", "prefer_when": None}]


def test_result_to_dict_has_every_envelope_field() -> None:
    d = r.Selector(PATTERNS, embedder=None, gate=r.GATE_OFF).select("requests", k=1).to_dict()
    assert set(d) == {"hits", "retrieval_path", "catalog_version", "auth", "empty_message"}
    assert d["auth"] == {"subject": "stdio-local"}


def test_empty_catalog_gives_the_empty_message() -> None:
    res = r.Selector([], embedder=r.HashEmbedder(), gate=r.GATE_OFF).select("anything", k=3)
    assert res.hits == [] and res.empty_message == r.EMPTY_MESSAGE


def test_cli_rejects_facet_without_equals() -> None:
    from agentic_patterns_catalog import cli
    assert cli.main(["select", "route", "--facet", "scale"]) == 2


def test_facet_arg_accepts_name_equals_value() -> None:
    assert r.facet_arg("scale=fleet") == ("scale", "fleet")


def test_default_embedder_is_none_when_the_model_cannot_load(monkeypatch, capsys) -> None:
    def boom(self, model_name: str = "x") -> None:
        raise ValueError("no model")
    monkeypatch.setattr(r.FastEmbedEmbedder, "__init__", boom)
    assert r.default_embedder() is None
    assert capsys.readouterr().err.strip() == "semantic arm off: ValueError: no model"


def test_select_rejects_unknown_facets_and_bad_k() -> None:
    sel = r.Selector(PATTERNS, embedder=None, gate=r.GATE_OFF)
    with pytest.raises(ValueError, match="unknown facet 'colour'"):
        sel.select("x", facets={"colour": "blue"})
    with pytest.raises(ValueError, match="unknown value 'galaxy' for facet 'scale'"):
        sel.select("x", facets={"scale": "galaxy"})
    with pytest.raises(ValueError, match="k must be >= 1"):
        sel.select("x", k=0)


def test_cli_rejects_unknown_facet_with_usage_exit(capsys) -> None:
    from agentic_patterns_catalog import cli
    assert cli.main(["select", "route", "--no-embed", "--facet", "colour=blue"]) == 2
    assert "unknown facet 'colour'" in capsys.readouterr().err


def test_cli_json_envelope_on_a_tiny_catalog(tmp_path, capsys) -> None:
    import json

    from agentic_patterns_catalog import cli
    from agentic_patterns_catalog.store import FileStore
    fs = FileStore(tmp_path, tmp_path / "cache")
    fs.put(PATTERNS[0])
    fs.put(PATTERNS[1])
    assert cli.main(["select", "route", "--no-embed", "--json", "--root", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"hits", "retrieval_path", "catalog_version", "auth", "empty_message"}
    assert (tmp_path / "patterns" / "routing" / "content-routing.json").exists()


def test_embedding_cache_path_flattens_the_model_name(tmp_path) -> None:
    assert r.embedding_cache_path("BAAI/bge-small-en-v1.5", tmp_path) == tmp_path / "BAAI_bge-small-en-v1.5.npy"


def test_embedding_cache_round_trip_matches_a_fresh_embed(tmp_path) -> None:
    embedder = r.HashEmbedder()
    path = r.build_embedding_cache(PATTERNS, embedder, tmp_path)
    assert path == r.embedding_cache_path(embedder.name, tmp_path)
    fresh = embedder.embed([r.pattern_text(p) for p in sorted(PATTERNS, key=lambda p: p.id)])
    loaded = r.load_embedding_cache(PATTERNS, embedder.name, tmp_path)
    assert loaded is not None and np.array_equal(loaded, fresh)
    assert json.loads(path.with_suffix(".json").read_text(encoding="utf-8")) == {
        "model": embedder.name, "ids": sorted(p.id for p in PATTERNS), "dim": fresh.shape[1],
        "content_version": content_version(PATTERNS)}


def test_embedding_cache_is_a_miss_when_the_ids_changed(tmp_path) -> None:
    r.build_embedding_cache(PATTERNS, r.HashEmbedder(), tmp_path)
    assert r.load_embedding_cache(PATTERNS[:2], r.HashEmbedder.name, tmp_path) is None


def test_embedding_cache_is_a_miss_for_another_model(tmp_path) -> None:
    r.build_embedding_cache(PATTERNS, r.HashEmbedder(), tmp_path)
    assert r.load_embedding_cache(PATTERNS, "some-other-model", tmp_path) is None


def test_absent_embedding_cache_is_a_miss_not_an_error(tmp_path) -> None:
    assert r.load_embedding_cache(PATTERNS, r.HashEmbedder.name, tmp_path) is None


def test_selector_uses_the_cache_when_it_hits(monkeypatch) -> None:
    fresh = r.HashEmbedder().embed([r.pattern_text(p) for p in sorted(PATTERNS, key=lambda p: p.id)])
    monkeypatch.setattr(r, "load_embedding_cache", lambda patterns, name, *a, **kw: fresh)
    sel = r.Selector(PATTERNS, embedder=r.HashEmbedder(), gate=r.GATE_OFF)
    assert sel._vectors is fresh
    assert sel.select("route requests by content to a handler", k=1).hits[0].id == "content-routing"


def test_selector_still_works_with_the_embedding_cache_off() -> None:
    sel = r.Selector(PATTERNS, embedder=r.HashEmbedder(), embedding_cache=False, gate=r.GATE_OFF)
    res = sel.select("route requests by content to a handler", k=3)
    assert res.retrieval_path == "rrf" and res.hits[0].id == "content-routing"


def test_embedding_cache_is_a_miss_when_a_record_content_changed(tmp_path) -> None:
    r.build_embedding_cache(PATTERNS, r.HashEmbedder(), tmp_path)
    edited = [*PATTERNS[:2], _p("reflection", "Model rewrites its own draft after a critique.")]
    assert content_version(edited) != content_version(PATTERNS)
    assert r.load_embedding_cache(edited, r.HashEmbedder.name, tmp_path) is None


def test_gate_returns_empty_when_relevance_is_below_the_threshold() -> None:
    sel = r.Selector(PATTERNS, embedder=r.HashEmbedder(), gate=r.Gate(1000.0))
    res = sel.select("route requests by content to a handler", k=3)
    assert res.hits == [] and res.empty_message == r.EMPTY_MESSAGE


def test_one_arm_selectors_are_never_gated() -> None:
    task = "route requests by content to a handler"
    bm_only = r.Selector(PATTERNS, embedder=None, gate=r.Gate(1000.0)).select(task, k=3)
    sem_only = r.Selector(PATTERNS, embedder=r.HashEmbedder(), arms=("semantic",), gate=r.Gate(1000.0)).select(task, k=3)
    assert bm_only.hits[0].id == "content-routing" and bm_only.empty_message is None
    assert sem_only.hits and sem_only.empty_message is None


def test_relevance_combines_both_signals() -> None:
    assert r.relevance(6.0, 0.5) == pytest.approx(1.0)
    assert r.relevance(0.0, 0.6) == pytest.approx(1.0)
    assert r.relevance(0.0, 0.2) == 0.0  # cosine below the base adds nothing


def test_gate_off_when_the_gate_file_is_missing_or_lacks_the_key(tmp_path: Path) -> None:
    assert r.load_gate(tmp_path / "absent.json") == r.GATE_OFF
    p = tmp_path / "gate.json"
    p.write_text('{"source": "x"}')
    assert r.load_gate(p) == r.GATE_OFF
    p.write_text('{"query_gate_threshold": 3.5}')
    assert r.load_gate(p) == r.Gate(3.5)


def test_committed_gate_keeps_every_ontopic_golden_case_and_blocks_every_offtopic_probe() -> None:
    from agentic_patterns_catalog import evaluate, store
    ids = {p.id for p in store.FileStore().all()}
    embedder = r.default_embedder() if len(ids) >= 288 else None
    if embedder is None:
        pytest.skip("needs the full local catalog and the embed extra")
    sel = r.Selector.from_store(store.FileStore(), embedder)
    for t in evaluate.load_tasks():
        if t.get("gap"):
            continue
        res = sel.select(t["task"], k=5)
        if t.get("expect_empty"):
            assert res.empty_message == r.EMPTY_MESSAGE, t["id"]
        else:
            assert res.hits, t["id"]
