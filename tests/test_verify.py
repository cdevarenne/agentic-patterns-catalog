import json
from pathlib import Path

from agentic_patterns_catalog import compile as comp
from agentic_patterns_catalog import schema, store, verify
from agentic_patterns_catalog.model import (
    Content,
    Pattern,
    Provenance,
    Relation,
    Selection,
    Source,
    Tldr,
    content_hash,
)
from agentic_patterns_catalog.paths import EVAL_THRESHOLDS, VOCAB_PATH


def _p(id: str, **sel) -> Pattern:
    c = Content(description=id, tldr=Tldr(what="w", when="n", watchOut="o"))
    return Pattern(id=id, name=id, category="routing", complexity="low", content=c, selection=Selection(**sel),
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


def _ctx(tmp_path: Path, **over) -> verify.VerifyContext:
    root = tmp_path / "catalog"
    (root / "categories").mkdir(parents=True, exist_ok=True)
    (root / "recipes").mkdir(exist_ok=True)
    (root / "vocab").mkdir(exist_ok=True)
    (root / "vocab" / "facets.json").write_text(VOCAB_PATH.read_text())
    fs = store.FileStore(root)
    fs.put(_p("a"))
    fs.put(_p("b", relations=[Relation(type="precedes", target="a")]))
    store.write_index(fs, root / "index.json")
    gen = tmp_path / "gen"
    comp.write_all(fs, gen)
    sch = tmp_path / "schema"
    schema.write_schemas(sch)
    base = {"root": root, "lenient_vocab": False, "generated_dir": gen, "schema_dir": sch,
            "eval_path": tmp_path / "eval.json", "thresholds_path": EVAL_THRESHOLDS}
    base.update(over)
    return verify.VerifyContext(**base)


def test_clean_tree_has_no_problems(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    assert {k: v for k, v in verify.run_checks(ctx).items() if v} == {}
    assert "eval" in verify.run_warnings(ctx)  # eval.json absent → warning, not error


def test_stale_index_and_bad_hash_are_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.root / "index.json").write_text(json.dumps({"patterns": {}, "categories": [], "recipes": []}))
    path = ctx.root / "patterns" / "routing" / "a.json"
    data = json.loads(path.read_text())
    data["provenance"]["source"]["content_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    problems = verify.run_checks(ctx)
    assert problems["index"] and problems["records"]


def test_precedes_cycle_and_unknown_target_are_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    fs = store.FileStore(ctx.root)
    fs.put(_p("a", relations=[Relation(type="precedes", target="b"), Relation(type="requires", target="zzz")]))
    problems = verify.run_checks(ctx)["relations"]
    assert any("cycle" in p for p in problems) and any("zzz" in p for p in problems)


def _write_raw_bad_facet(ctx: verify.VerifyContext) -> None:
    # The model rejects unknown values, so a file with one can only come from a raw write
    # (or from a vocabulary edited after the record was written).
    path = ctx.root / "patterns" / "routing" / "a.json"
    data = json.loads(path.read_text())
    data["selection"]["facets"]["scale"] = "galaxy"
    path.write_text(json.dumps(data))


def test_unknown_facet_is_a_problem_unless_lenient(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _write_raw_bad_facet(ctx)
    assert verify.check_facets(ctx) == ["a: scale=galaxy"]
    assert "facets" not in verify.run_warnings(ctx)
    lenient = _ctx(tmp_path, lenient_vocab=True)
    _write_raw_bad_facet(lenient)
    assert verify.check_facets(lenient) == []
    assert verify.run_warnings(lenient)["facets"] == ["a: scale=galaxy"]


def test_stale_compiled_output_is_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.generated_dir / "CATALOG.md").write_text("edited by hand\n")
    assert verify.run_checks(ctx)["compiled"] == ["CATALOG.md differs from a fresh compile"]


def test_repo_verifies_clean() -> None:
    # Committed index.json and generated/ reflect all 288 records. A checkout without the local
    # mirror (CI) holds 11, so `index` and `compiled` are expected to differ there and are skipped.
    ctx = verify.VerifyContext.default()
    indexed = len(json.loads((ctx.root / "index.json").read_text())["patterns"])
    partial = len(store.FileStore(ctx.root).all()) < indexed
    skipped = {"index", "compiled"} if partial else set()
    problems = {k: v for k, v in verify.run_checks(ctx).items() if v and k not in skipped}
    assert problems == {}, problems
