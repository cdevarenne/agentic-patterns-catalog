"""Measure the scores that justify the relevance gate, and write the record the gate threshold is derived from."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
from pathlib import Path
from typing import Any

from .cli import register
from .evaluate import load_tasks
from .paths import CATALOG_DIR, DATA_DIR
from .retrieval import GATE_OFF, Embedder, Selector, default_embedder, relevance
from .store import FileStore, Store, content_version, git_ref


def _summary(xs: list[float]) -> dict[str, float | int]:
    return {"n": len(xs), "min": min(xs, default=0.0), "median": statistics.median(xs) if xs else 0.0,
            "max": max(xs, default=0.0)}


def run(store: Store, tasks: list[dict[str, Any]], embedder: Embedder | None, k: int = 10) -> dict[str, Any]:
    """Top scores per on-topic and off-topic query, true-hit scores, and the gate threshold they suggest."""
    patterns = store.all()
    selector = Selector(patterns, embedder, gate=GATE_OFF)  # measure with the gate off
    on_bm, on_sem, off_bm, off_sem, on_rel, off_rel, hit_bm, hit_sem = [], [], [], [], [], [], [], []
    for t in tasks:
        if t.get("gap"):
            continue
        bm, sem = selector.arm_scores(t["task"], t.get("facets"))  # the same maxima the gate reads
        tb, ts = max(bm.values(), default=0.0), max(sem.values(), default=0.0)
        res = selector.select(t["task"], t.get("facets"), k)
        if t.get("expect_empty"):
            off_bm.append(tb)
            off_sem.append(ts)
            off_rel.append(relevance(tb, ts))
            continue
        on_bm.append(tb)
        on_sem.append(ts)
        on_rel.append(relevance(tb, ts))
        for h in res.hits:
            if h.id in t["expected_ids"]:
                if h.score_bm25 is not None:
                    hit_bm.append(h.score_bm25)
                if h.score_semantic is not None:
                    hit_sem.append(h.score_semantic)
    on_min, off_max = min(on_rel, default=0.0), max(off_rel, default=0.0)
    return {
        "run": {"catalog_version": content_version(patterns), "git_ref": git_ref(),
                "embed_model": embedder.name if embedder else None,
                "date": dt.datetime.now(dt.UTC).date().isoformat(), "k": k},
        "ontopic": {"top_bm25": _summary(on_bm), "top_semantic": _summary(on_sem)},
        "offtopic": {"top_bm25": _summary(off_bm), "top_semantic": _summary(off_sem)},
        "true_hits": {"bm25": _summary(hit_bm), "semantic": _summary(hit_sem)},
        "separable": {"bm25": max(off_bm, default=0.0) < min(on_bm, default=0.0),
                      "semantic": max(off_sem, default=0.0) < min(on_sem, default=0.0),
                      "relevance": off_max < on_min},
        "relevance": {"ontopic_min": on_min, "offtopic_max": off_max, "margin": on_min - off_max},
        "suggested": {"query_gate_threshold": round((off_max + on_min) / 2, 2)},
    }


def write(report: dict[str, Any], path: Path = DATA_DIR / "floor-calibration.json") -> Path:
    """Write the record as sorted, indented JSON and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


@register("calibrate", "measure the scores behind the relevance gate and write docs/data/floor-calibration.json")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--no-embed", action="store_true")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)

    def run_cmd(ns: argparse.Namespace) -> int:
        report = run(FileStore(ns.root), load_tasks(), None if ns.no_embed else default_embedder(), ns.k)
        path = write(report)
        print(json.dumps({"separable": report["separable"], "relevance": report["relevance"],
                          "suggested": report["suggested"]}))
        print(f"wrote {path}")
        return 0
    return run_cmd
