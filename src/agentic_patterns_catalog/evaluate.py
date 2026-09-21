"""Golden-set evaluation of `select`, one arm at a time. Writes a record; prose cites it."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from .cli import register
from .paths import CATALOG_DIR, DATA_DIR, EVAL_TASKS, EVAL_THRESHOLDS
from .retrieval import Embedder, Gate, Selector, default_embedder
from .store import FileStore, Store, content_version, git_ref

ARMS = {"bm25": ("bm25",), "semantic": ("semantic",), "rrf": ("bm25", "semantic")}


def load_tasks(path: Path = EVAL_TASKS) -> list[dict[str, Any]]:
    """Read the golden set: one JSON task per non-blank line."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _score_arm(store: Store, tasks: list[dict[str, Any]], embedder: Embedder | None, arms: tuple[str, ...],
               k: int, gate: Gate | None) -> dict[str, Any] | None:
    if arms == ("semantic",) and embedder is None:
        return None  # the rrf arm degrades to bm25; run.embed_model records that
    selector = Selector.from_store(store, embedder, arms, gate)
    cases = []
    for t in tasks:
        res = selector.select(t["task"], t.get("facets"), k)
        top = [h.id for h in res.hits]
        if t.get("expect_empty"):
            hit, rr = res.empty_message is not None, 0.0
        else:
            ranks = [top.index(e) + 1 for e in t["expected_ids"] if e in top]
            hit, rr = bool(ranks), (1.0 / min(ranks) if ranks else 0.0)
        cases.append({"id": t["id"], "expected_ids": t["expected_ids"], "top": top, "hit": hit,
                      "reciprocal_rank": rr, "expect_empty": bool(t.get("expect_empty")),
                      "scores": [{"id": h.id, "score_bm25": h.score_bm25, "score_semantic": h.score_semantic}
                                 for h in res.hits]})
    on = [c for c in cases if not c["expect_empty"]]
    off = [c for c in cases if c["expect_empty"]]
    return {"hit_at_k": _mean([c["hit"] for c in on]), "mrr": _mean([c["reciprocal_rank"] for c in on]),
            "offtopic_empty_rate": _mean([c["hit"] for c in off], empty=1.0),
            "ontopic_kept_rate": _mean([bool(c["top"]) for c in on]), "cases": cases}


def _mean(xs: list[float], empty: float = 0.0) -> float:
    return sum(xs) / len(xs) if xs else empty


def run_eval(store: Store, tasks: list[dict[str, Any]], embedder: Embedder | None, k: int = 5,
             gate: Gate | None = None) -> dict[str, Any]:
    """Score every arm on the non-gap tasks and return the report (`run` block plus per-arm results).

    `gate=None` reads the committed gate from `eval/gate.json`; tests on a toy corpus pass `GATE_OFF`.
    """
    scored = [t for t in tasks if not t.get("gap")]
    return {
        "run": {"catalog_version": content_version(store.all()), "git_ref": git_ref(),
                "embed_model": embedder.name if embedder else None,
                "date": dt.datetime.now(dt.UTC).date().isoformat(), "k": k, "cases": len(scored),
                "gaps": len(tasks) - len(scored), "offtopic": sum(bool(t.get("expect_empty")) for t in scored)},
        "arms": {name: _score_arm(store, scored, embedder, arms, k, gate) for name, arms in ARMS.items()},
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
    """Write the report as sorted, indented JSON and return the path."""
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
            print(f"{arm:9s} " + ("not run" if r is None else
                                   f"hit@{ns.k}={r['hit_at_k']:.3f} mrr={r['mrr']:.3f} "
                                   f"offtopic_empty_rate={r['offtopic_empty_rate']:.3f} "
                                   f"ontopic_kept_rate={r['ontopic_kept_rate']:.3f}"))
        problems = check_thresholds(report, json.loads(EVAL_THRESHOLDS.read_text(encoding="utf-8")))
        print(f"wrote {path}" + (f"; below threshold: {', '.join(problems)}" if problems else ""))
        return 1 if problems else 0
    return run
