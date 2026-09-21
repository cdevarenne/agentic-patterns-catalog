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
    cache = tmp_path / "cache"
    fs = store.FileStore(root, cache)
    fs.put(_p("a"))
    fs.put(_p("b", relations=[Relation(type="precedes", target="a")]))
    store.write_index(fs, root / "index.json")
    gen = tmp_path / "gen"
    comp.write_all(fs, gen)
    sch = tmp_path / "schema"
    schema.write_schemas(sch)
    base = {"root": root, "lenient_vocab": False, "generated_dir": gen, "schema_dir": sch,
            "eval_path": tmp_path / "eval.json", "thresholds_path": EVAL_THRESHOLDS, "cache": cache}
    base.update(over)
    return verify.VerifyContext(**base)


def test_clean_tree_has_no_problems(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    assert {k: v for k, v in verify.run_checks(ctx).items() if v} == {}
    assert "eval" in verify.run_warnings(ctx)  # eval.json absent → warning, not error


def test_missing_cached_content_is_a_warning_not_a_problem(tmp_path: Path) -> None:
    # With no cached content, check_records has nothing to compare a hash against, so this is a
    # warning ("run `catalog extract`"), not a "records" problem.
    ctx = _ctx(tmp_path)
    for path in ctx.cache.glob("*/*.json"):
        path.unlink()
    assert verify.run_checks(ctx)["records"] == []
    assert "content" in verify.run_warnings(ctx)


def test_stale_index_and_bad_hash_are_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.root / "index.json").write_text(json.dumps({"patterns": {}, "categories": [], "recipes": []}))
    path = ctx.root / "patterns" / "routing" / "a.json"
    data = json.loads(path.read_text())
    data["provenance"]["source"]["content_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    problems = verify.run_checks(ctx)
    assert problems["index"]
    assert any("content_sha256 does not match content" in p for p in problems["records"])


def test_stale_index_and_bad_id_are_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.root / "index.json").write_text(json.dumps({"patterns": {}, "categories": [], "recipes": []}))
    path = ctx.root / "patterns" / "routing" / "a.json"
    data = json.loads(path.read_text())
    data["id"] = "not-a"
    path.write_text(json.dumps(data))
    problems = verify.run_checks(ctx)
    assert problems["index"] and problems["records"]


def test_precedes_cycle_and_unknown_target_are_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    fs = store.FileStore(ctx.root, ctx.cache)
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


def test_malformed_category_is_reported_and_no_check_raises(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.root / "categories" / "x.json").write_text(json.dumps({"id": "x"}))
    (ctx.root / "recipes" / "r.json").write_text(json.dumps({"id": "r", "name": "R"}))
    problems = verify.run_checks(ctx)["records"]
    assert any(p.startswith("x.json: ") for p in problems), problems
    assert any(p.startswith("r.json: ") for p in problems), problems


def test_index_entry_drift_and_list_drift_are_reported(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    path = ctx.root / "index.json"
    idx = json.loads(path.read_text())
    idx["patterns"]["a"]["reviewed"] = True
    idx["categories"] = ["ghost"]
    path.write_text(json.dumps(idx))
    problems = verify.run_checks(ctx)["index"]
    assert "index.json: stale entry for a" in problems
    assert any("categories" in p for p in problems), problems


def test_file_not_produced_by_compile_is_reported_and_removed(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    extra = ctx.generated_dir / "sheets" / "zzz.md"
    extra.parent.mkdir(exist_ok=True)
    extra.write_text("stale\n")
    (ctx.generated_dir / "local" / "keep.md").parent.mkdir()
    (ctx.generated_dir / "local" / "keep.md").write_text("local output is never touched\n")
    assert verify.run_checks(ctx)["compiled"] == ["sheets/zzz.md is not produced by compile; remove it"]
    _, removed = comp.write_all(store.FileStore(ctx.root, ctx.cache), ctx.generated_dir)
    assert removed == [extra] and not extra.exists() and (ctx.generated_dir / "local" / "keep.md").exists()
    assert verify.run_checks(ctx)["compiled"] == []


def test_cli_skip_does_not_run_the_skipped_check(monkeypatch) -> None:
    from agentic_patterns_catalog import cli

    ran: list[str] = []

    def spy(ctx: verify.VerifyContext) -> list[str]:
        ran.append("records")
        return ["must not be reported"]
    monkeypatch.setattr(verify, "CHECKS", [("records", spy), *verify.CHECKS[1:]])
    # index and compiled are skipped as well so the test passes on a checkout without the 277 local records
    assert cli.main(["verify", "--skip", "records,index,compiled"]) == 0
    assert ran == []


def test_a_check_that_raises_is_reported_not_propagated(tmp_path: Path, monkeypatch) -> None:
    def boom(ctx: verify.VerifyContext) -> list[str]:
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(verify, "CHECKS", [("records", boom)])
    assert verify.run_checks(_ctx(tmp_path)) == {"records": ["check could not run: RuntimeError: disk on fire"]}


def test_repo_verifies_clean() -> None:
    # Committed index.json and generated/ reflect all 288 records. A checkout without the local
    # mirror (CI) holds 11, so `index` and `compiled` are expected to differ there and are skipped.
    ctx = verify.VerifyContext.default()
    indexed = len(json.loads((ctx.root / "index.json").read_text())["patterns"])
    partial = len(store.FileStore(ctx.root, ctx.cache).all()) < indexed
    skipped = {"index", "compiled"} if partial else set()
    problems = {k: v for k, v in verify.run_checks(ctx).items() if v and k not in skipped}
    assert problems == {}, problems
