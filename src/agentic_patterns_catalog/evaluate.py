"""Golden-set evaluation of `select`, one arm at a time. Writes a record; prose cites it."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from .cli import register
from .paths import CATALOG_DIR, DATA_DIR, EVAL_TASKS, EVAL_THRESHOLDS
from .retrieval import Embedder, Selector, default_embedder
from .store import FileStore, Store, catalog_version

ARMS = {"bm25": ("bm25",), "semantic": ("semantic",), "rrf": ("bm25", "semantic")}


def load_tasks(path: Path = EVAL_TASKS) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _score_arm(store: Store, tasks: list[dict[str, Any]], embedder: Embedder | None, arms: tuple[str, ...],
               k: int) -> dict[str, Any] | None:
    if arms == ("semantic",) and embedder is None:
        return None  # the rrf arm degrades to bm25; run.embed_model records that
    selector = Selector.from_store(store, embedder, arms)
    cases = []
    for t in tasks:
        top = [h.id for h in selector.select(t["task"], t.get("facets"), k).hits]
        ranks = [top.index(e) + 1 for e in t["expected_ids"] if e in top]
        rr = 1.0 / min(ranks) if ranks else 0.0
        cases.append({"id": t["id"], "expected_ids": t["expected_ids"], "top": top, "hit": bool(ranks),
                      "reciprocal_rank": rr})
    n = len(cases) or 1
    return {"hit_at_k": sum(c["hit"] for c in cases) / n, "mrr": sum(c["reciprocal_rank"] for c in cases) / n,
            "cases": cases}


def run_eval(store: Store, tasks: list[dict[str, Any]], embedder: Embedder | None, k: int = 5) -> dict[str, Any]:
    scored = [t for t in tasks if not t.get("gap")]
    return {
        "run": {"catalog_version": catalog_version(), "embed_model": embedder.name if embedder else None,
                "date": dt.datetime.now(dt.UTC).date().isoformat(), "k": k, "cases": len(scored),
                "gaps": len(tasks) - len(scored)},
        "arms": {name: _score_arm(store, scored, embedder, arms, k) for name, arms in ARMS.items()},
    }


def check_thresholds(report: dict[str, Any], thresholds: dict[str, float]) -> list[str]:
    """`<arm>_<metric>` thresholds that the report does not meet."""
    problems = []
    for key, floor in thresholds.items():
        arm, metric = key.split("_", 1)
        got = (report["arms"].get(arm) or {}).get(metric)
        if got is None or got < floor:
            problems.append(f"{key} {got if got is None else f'{got:.3f}'} < {floor:.3f}")
    return problems


def write_eval(report: dict[str, Any], path: Path = DATA_DIR / "eval.json") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


@register("eval", "run the golden set through every arm and write docs/data/eval.json")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--no-embed", action="store_true")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)

    def run(ns: argparse.Namespace) -> int:
        embedder = None if ns.no_embed else default_embedder()
        report = run_eval(FileStore(ns.root), load_tasks(), embedder, ns.k)
        path = write_eval(report)
        for arm, r in report["arms"].items():
            print(f"{arm:9s} " + ("not run" if r is None else f"hit@{ns.k}={r['hit_at_k']:.3f} mrr={r['mrr']:.3f}"))
        problems = check_thresholds(report, json.loads(EVAL_THRESHOLDS.read_text(encoding="utf-8")))
        print(f"wrote {path}" + (f"; below threshold: {', '.join(problems)}" if problems else ""))
        return 1 if problems else 0
    return run
