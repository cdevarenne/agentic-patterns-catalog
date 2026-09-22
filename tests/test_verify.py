import json
import shutil
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
    dumps,
)
from agentic_patterns_catalog.paths import EVAL_THRESHOLDS, VOCAB_PATH


def _p(id: str, extraction: str = "rsc-payload", **sel) -> Pattern:
    c = Content(description=id, tldr=Tldr(what="w", when="n", watchOut="o"))
    return Pattern(id=id, name=id, category="routing", complexity="low", content=c, selection=Selection(**sel),
                   provenance=Provenance(source=Source(url="u", extraction=extraction, content_sha256=content_hash(c))))


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
    warning = verify.run_warnings(ctx)["content"][0]
    assert "catalog extract" in warning and "catalog seed" in warning


def test_without_a_cache_only_compiled_fails(tmp_path: Path) -> None:
    # A fresh clone has records and no cache. Every identity-level check passes there; only the
    # compiled views differ, because the committed pack sheets need the cached prose.
    ctx = _ctx(tmp_path)
    fs = store.FileStore(ctx.root, ctx.cache)
    fs.put(_p("c", "free-pack"))
    store.write_index(fs, ctx.root / "index.json")
    comp.write_all(fs, ctx.generated_dir)
    shutil.rmtree(ctx.cache)
    problems = verify.run_checks(ctx)
    assert problems["records"] == []
    assert {name for name, items in problems.items() if items} == {"compiled"}


def test_malformed_cached_content_is_reported_and_does_not_abort(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.cache / "routing" / "a.json").write_text("{not json")
    problems = verify.run_checks(ctx)
    assert any("a: cached content does not parse" in p for p in problems["records"])
    # The loop continued: record "b" (valid cache) still had its hash checked and passed.
    assert not any(p.startswith("b:") for p in problems["records"])


def test_tracked_record_with_a_content_key_is_reported(tmp_path: Path) -> None:
    # Site prose in a tracked file would be committed and, for 277 records, redistributed.
    ctx = _ctx(tmp_path)
    (ctx.root / "patterns" / "routing" / "a.json").write_text(dumps(_p("a")), encoding="utf-8")
    assert "a.json: tracked record carries a content key; write it with dumps_record" in verify.run_checks(ctx)["records"]


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
    # index and compiled are skipped as well so the test passes on a checkout with no content cache
    assert cli.main(["verify", "--skip", "records,index,compiled"]) == 0
    assert ran == []


def test_a_check_that_raises_is_reported_not_propagated(tmp_path: Path, monkeypatch) -> None:
    def boom(ctx: verify.VerifyContext) -> list[str]:
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(verify, "CHECKS", [("records", boom)])
    assert verify.run_checks(_ctx(tmp_path)) == {"records": ["check could not run: RuntimeError: disk on fire"]}


def test_repo_verifies_clean() -> None:
    # All 288 records are tracked, so `index` passes with or without a content cache. The committed
    # pack sheets need cached prose: on a checkout whose cache is missing or partial (a fresh clone,
    # or `catalog extract` without `catalog seed`) `compiled` differs and is the one check skipped.
    ctx = verify.VerifyContext.default()
    partial = any(p.content is None for p in store.FileStore(ctx.root, ctx.cache).all())
    skipped = {"compiled"} if partial else set()
    problems = {k: v for k, v in verify.run_checks(ctx).items() if v and k not in skipped}
    assert problems == {}, problems


def test_pg_check_skips_without_dsn_and_reports_drift_with_one(monkeypatch, tmp_path, pg_dsn, pg_schema) -> None:
    from tests.test_server import _p

    from agentic_patterns_catalog import pgstore
    fs = store.FileStore(tmp_path, tmp_path / "cache")
    fs.put(_p("content-router"))
    ctx = verify.VerifyContext(tmp_path, False, tmp_path, tmp_path, tmp_path / "eval.json", tmp_path / "t.json", tmp_path / "cache")
    monkeypatch.delenv("CATALOG_PG_DSN", raising=False)
    assert verify.check_pg(ctx) == []
    monkeypatch.setenv("CATALOG_PG_DSN", pg_dsn)
    monkeypatch.setenv("CATALOG_PG_SCHEMA", pg_schema)
    pg = pgstore.PostgresStore(pg_dsn, schema=pg_schema)
    pg.ensure_schema()
    assert verify.check_pg(ctx) == ["postgres holds 0 patterns, files hold 1; run `catalog sync-pg`"]
    pg.sync_from(fs)
    assert verify.check_pg(ctx) == []
