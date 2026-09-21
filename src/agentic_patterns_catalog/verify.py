"""One command that checks the whole catalog. Exit 1 on any problem; warnings do not fail."""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from . import compile as comp
from . import vocab as vocab_mod
from .cli import register
from .evaluate import check_thresholds
from .model import Category, Content, Pattern, Recipe, content_hash
from .paths import (
    CATALOG_DIR,
    CONTENT_CACHE_DIR,
    DATA_DIR,
    EVAL_THRESHOLDS,
    GENERATED_DIR,
    SCHEMA_DIR,
)
from .schema import schemas_match
from .store import FileStore, build_index


@dataclass
class VerifyContext:
    """Where one verification run reads from. `lenient_vocab` turns unknown facet values into warnings."""
    root: Path
    lenient_vocab: bool
    generated_dir: Path
    schema_dir: Path
    eval_path: Path
    thresholds_path: Path
    cache: Path = CONTENT_CACHE_DIR

    @classmethod
    def default(cls, lenient_vocab: bool = False) -> VerifyContext:
        return cls(CATALOG_DIR, lenient_vocab, GENERATED_DIR, SCHEMA_DIR, DATA_DIR / "eval.json", EVAL_THRESHOLDS,
                    CONTENT_CACHE_DIR)


Check = Callable[[VerifyContext], list[str]]


def _first_error(e: ValidationError) -> str:
    err = e.errors()[0]
    return f"{err['msg']} at {err['loc']}"


def check_records(ctx: VerifyContext) -> list[str]:
    """Every pattern, category and recipe file validates; pattern id, directory and content hash agree.

    The tracked file never carries content (it is cache), so this attaches whatever is cached
    before the hash check, the same way `FileStore._load` does. A record with nothing cached
    skips the hash check; a cache file that fails to parse is a problem, not a crash.
    """
    problems = []
    fs = FileStore(ctx.root, ctx.cache)
    for sub, model in (("categories", Category), ("recipes", Recipe)):
        for path in sorted((ctx.root / sub).glob("*.json")):
            try:
                model.model_validate_json(path.read_text(encoding="utf-8"))
            except ValidationError as e:
                problems.append(f"{path.name}: {_first_error(e)}")
    for path in sorted((ctx.root / "patterns").glob("*/*.json")):
        try:
            p = Pattern.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as e:
            problems.append(f"{path.name}: {_first_error(e)}")
            continue
        if p.id != path.stem:
            problems.append(f"{path.name}: id {p.id!r} != file stem")
        if p.category != path.parent.name:
            problems.append(f"{path.name}: category {p.category!r} != directory {path.parent.name!r}")
        cached = fs.cache_path(p.category, p.id)
        if cached.is_file():
            try:
                p = p.model_copy(update={"content": Content.model_validate_json(cached.read_text(encoding="utf-8"))})
            except ValidationError as e:
                problems.append(f"{p.id}: cached content does not parse: {_first_error(e)}")
                continue
        if p.content is not None and p.provenance.source.content_sha256 != content_hash(p.content):
            problems.append(f"{p.id}: content_sha256 does not match content")
    return problems


def check_index(ctx: VerifyContext) -> list[str]:
    """Committed index.json equals a fresh one: every pattern entry, and the category and recipe lists."""
    path = ctx.root / "index.json"
    if not path.exists():
        return ["index.json missing; run `catalog index`"]
    committed = json.loads(path.read_text(encoding="utf-8"))
    fresh = build_index(FileStore(ctx.root, ctx.cache))
    problems = []
    if set(committed.get("patterns", {})) != set(fresh["patterns"]):
        problems.append("index.json pattern ids differ from files on disk")
    for id, entry in fresh["patterns"].items():
        c = committed.get("patterns", {}).get(id)
        if c is not None and c != entry:
            problems.append(f"index.json: stale entry for {id}")
    for key in ("categories", "recipes"):
        if committed.get(key) != fresh[key]:
            problems.append(f"index.json: {key} list differs from files on disk")
    return problems


def _relations(ctx: VerifyContext) -> tuple[dict[str, Pattern], list[str]]:
    by_id = {p.id: p for p in FileStore(ctx.root, ctx.cache).all()}
    problems = []
    for p in by_id.values():
        for r in p.selection.relations:
            if r.target not in by_id:
                problems.append(f"{p.id}: relation target {r.target!r} does not resolve")
    return by_id, problems


def check_relations(ctx: VerifyContext) -> list[str]:
    """Every relation target resolves and `precedes` edges form no cycle."""
    by_id, problems = _relations(ctx)
    graph = {p.id: [r.target for r in p.selection.relations if r.type == "precedes" and r.target in by_id]
             for p in by_id.values()}
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 1:
            problems.append("precedes cycle: " + " → ".join([*trail[trail.index(node):], node]))
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for nxt in graph.get(node, []):
            visit(nxt, [*trail, node])
        state[node] = 2

    for node in sorted(graph):
        if state.get(node) != 2:
            visit(node, [])
    return problems


def check_recipes(ctx: VerifyContext) -> list[str]:
    """Every recipe step names an existing pattern."""
    fs = FileStore(ctx.root, ctx.cache)
    ids = {p.id for p in fs.all()}
    return [f"recipe {r.id}: step {s.order} names unknown pattern {s.pattern_id!r}"
            for r in fs.recipes() for s in r.steps if s.pattern_id not in ids]


def check_schema(ctx: VerifyContext) -> list[str]:
    """Committed schema files equal a fresh generation from the models."""
    return [f"schema/{n}.schema.json is stale; run `catalog schema`" for n in schemas_match(ctx.schema_dir)]


def facet_problems(ctx: VerifyContext) -> list[str]:
    """`<id>: <facet>=<value>` for values absent from the vocabulary file under `ctx.root`.

    Reads the raw JSON: the model already rejects unknown values, so this covers files written
    raw and a vocabulary edited after the records were. Malformed files belong to `check_records`.
    """
    vocab = vocab_mod.load_vocab(ctx.root / "vocab" / "facets.json")
    out = []
    for path in sorted((ctx.root / "patterns").glob("*/*.json")):
        try:
            facets = json.loads(path.read_text(encoding="utf-8"))["selection"]["facets"]
        except (ValueError, KeyError, TypeError):
            continue
        out += [f"{path.stem}: {bad}" for bad in vocab_mod.unknown_facet_values(facets, vocab)]
    return out


def check_facets(ctx: VerifyContext) -> list[str]:
    """Unknown facet values are problems, except under `--lenient-vocab` (then `run_warnings` lists them)."""
    return [] if ctx.lenient_vocab else facet_problems(ctx)


def check_compiled(ctx: VerifyContext) -> list[str]:
    """Compiled views are under budget, equal a fresh compile, and nothing else sits in `generated/`."""
    outputs = comp.compile_all(FileStore(ctx.root, ctx.cache))
    problems = [f"{n} over budget ({comp.token_estimate(outputs[n])} > {comp.BUDGETS[n]} tokens)"
                for n in comp.over_budget(outputs)]
    for rel, text in outputs.items():
        path = ctx.generated_dir / rel
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            problems.append(f"{rel} differs from a fresh compile")
    problems += [f"{p.relative_to(ctx.generated_dir)} is not produced by compile; remove it"
                 for p in comp.stale_files(ctx.generated_dir, outputs)]
    return problems


def check_eval(ctx: VerifyContext) -> list[str]:
    """The eval record, when present, meets every threshold in `thresholds_path`."""
    if not ctx.eval_path.exists():
        return []
    report = json.loads(ctx.eval_path.read_text(encoding="utf-8"))
    return check_thresholds(report, json.loads(ctx.thresholds_path.read_text(encoding="utf-8")))


CHECKS: list[tuple[str, Check]] = [
    ("records", check_records), ("index", check_index), ("relations", check_relations), ("recipes", check_recipes),
    ("schema", check_schema), ("facets", check_facets), ("compiled", check_compiled), ("eval", check_eval),
]


def _guarded(check: Check, ctx: VerifyContext) -> list[str]:
    try:
        return check(ctx)
    except Exception as e:  # noqa: BLE001 — a check that cannot run is a problem to print, not a traceback
        return [f"check could not run: {type(e).__name__}: {str(e).splitlines()[0]}"]


def run_checks(ctx: VerifyContext, skip: Collection[str] = ()) -> dict[str, list[str]]:
    """Problems per check name, for every check not in `skip`. A check that raises reports one problem."""
    return {name: _guarded(check, ctx) for name, check in CHECKS if name not in skip}


def run_warnings(ctx: VerifyContext) -> dict[str, list[str]]:
    """Non-failing findings: unknown facet values under `--lenient-vocab`, a missing eval record, and
    records with no cached content."""
    warnings: dict[str, list[str]] = {}
    if ctx.lenient_vocab:
        bad = facet_problems(ctx)
        if bad:
            warnings["facets"] = bad
    if not ctx.eval_path.exists():
        warnings["eval"] = [f"{ctx.eval_path} absent; run `catalog eval`"]
    try:
        missing = [p.id for p in FileStore(ctx.root, ctx.cache).all() if p.content is None]
    except Exception:  # noqa: BLE001 — a malformed record already surfaces via check_records; this warning is best-effort
        missing = []
    if missing:
        warnings["content"] = [f"{len(missing)} records have no cached content; run `catalog extract`"]
    return warnings


@register("verify", "check records, index, relations, schema, facets, compiled views and eval")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--lenient-vocab", action="store_true",
                        help="unknown facet values warn instead of fail (vocabulary-discovery sessions only)")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)
    parser.add_argument("--skip", default="", metavar="NAME[,NAME]",
                        help="checks to skip, e.g. index,compiled on a checkout without the 277 local records")

    def run(ns: argparse.Namespace) -> int:
        ctx = VerifyContext.default(ns.lenient_vocab)
        ctx.root = ns.root
        problems = run_checks(ctx, skip={n for n in ns.skip.split(",") if n})
        for name, items in problems.items():
            print(f"{'FAIL' if items else 'ok  '} {name}" + (f" ({len(items)})" if items else ""))
            for item in items[:20]:
                print(f"       {item}")
        for name, items in run_warnings(ctx).items():
            print(f"warn {name}: {items[0]}" + (f" (+{len(items) - 1} more)" if len(items) > 1 else ""))
        return 1 if any(problems.values()) else 0
    return run
