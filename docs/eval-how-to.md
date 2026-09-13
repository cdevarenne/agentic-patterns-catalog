# How to run the evaluation

`uv run catalog eval` runs `eval/tasks.jsonl` through three arms of `select` (BM25, semantic, RRF)
and writes `docs/data/eval.json`. `eval/thresholds.json` names the floors `catalog verify` enforces.
The semantic arm needs the `embed` extra: `uv sync --extra embed`.

Illustrative output (pasted from a run; nothing asserts it):

```
# run 2026-09-12
bm25      hit@5=0.607 mrr=0.530
semantic  hit@5=0.643 mrr=0.614
rrf       hit@5=0.750 mrr=0.565
wrote /opt/devel/DevMoi/agentic-patterns-catalog/docs/data/eval.json
```

Results are the record, not this page. Quote figures from `docs/data/eval.json`.
