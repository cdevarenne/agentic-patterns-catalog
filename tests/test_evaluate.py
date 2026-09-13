import json
from pathlib import Path

import pytest

from agentic_patterns_catalog import evaluate, retrieval, store
from agentic_patterns_catalog.model import Content, Pattern, Provenance, Source, Tldr, content_hash


def _p(id: str, what: str) -> Pattern:
    c = Content(description=what, tldr=Tldr(what=what, when="", watchOut="w"))
    return Pattern(id=id, name=id, category="routing", complexity="low", content=c,
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


class _Mem:
    def __init__(self, ps): self._ps = ps
    def all(self): return self._ps
    def get(self, id): return next(p for p in self._ps if p.id == id)
    def put(self, p): pass
    def categories(self): return []
    def recipes(self): return []


TASKS = [
    {"id": "a", "task": "route by content", "expected_ids": ["content-routing"], "expected_path": "rrf"},
    {"id": "b", "task": "balance load across workers", "expected_ids": ["load-balancing"], "expected_path": "rrf"},
    {"id": "c", "task": "something absent", "expected_ids": [], "expected_path": "rrf", "gap": True},
]
STORE = _Mem([_p("content-routing", "routes requests by content"), _p("load-balancing", "balances load across workers"),
              _p("distractor-pattern", "schedules background maintenance jobs at night")])
# The distractor keeps the corpus at 3 documents: with exactly 2 fully disjoint-vocabulary
# documents, rank_bm25's idf is identically 0 for every term (log(N-df+0.5)-log(df+0.5) with
# N=2, df=1), so bm25 never distinguishes them. A neutral third document avoids that edge case.


def test_run_eval_scores_each_arm_and_skips_gaps() -> None:
    rep = evaluate.run_eval(STORE, TASKS, retrieval.HashEmbedder(), k=2)
    assert set(rep["arms"]) == {"bm25", "semantic", "rrf"}
    assert rep["arms"]["rrf"]["hit_at_k"] == 1.0 and rep["arms"]["rrf"]["mrr"] == 1.0
    assert rep["run"]["cases"] == 2 and rep["run"]["gaps"] == 1
    assert rep["run"]["embed_model"] == "hash-bow-256"


def test_semantic_arm_is_null_without_an_embedder() -> None:
    rep = evaluate.run_eval(STORE, TASKS, None, k=2)
    assert rep["arms"]["semantic"] is None and rep["arms"]["rrf"]["hit_at_k"] == 1.0


def test_thresholds_report_shortfalls() -> None:
    rep = evaluate.run_eval(STORE, TASKS, None, k=2)
    assert evaluate.check_thresholds(rep, {"rrf_hit_at_k": 0.5}) == []
    assert evaluate.check_thresholds(rep, {"rrf_hit_at_k": 1.5}) == ["rrf_hit_at_k 1.000 < 1.500"]


def test_write_eval_and_load_tasks_roundtrip(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text("\n".join(json.dumps(t) for t in TASKS) + "\n")
    assert [t["id"] for t in evaluate.load_tasks(tasks)] == ["a", "b", "c"]
    out = evaluate.write_eval(evaluate.run_eval(STORE, TASKS, None), tmp_path / "eval.json")
    assert json.loads(out.read_text())["run"]["k"] == 5


def test_committed_tasks_reference_existing_ids() -> None:
    ids = {p.id for p in store.FileStore().all()}
    if len(ids) < 288:
        pytest.skip("needs the full local catalog (288 records)")
    for t in evaluate.load_tasks():
        for e in t["expected_ids"]:
            assert e in ids, f"{t['id']}: unknown pattern id {e}"
