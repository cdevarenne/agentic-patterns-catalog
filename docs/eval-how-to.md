# How to run the evaluation

`uv run catalog eval` runs `eval/tasks.jsonl` through three arms of `select` (BM25, semantic, RRF)
and writes `docs/data/eval.json`. `eval/thresholds.json` names the floors `catalog verify` enforces.
The semantic arm needs the `embed` extra: `uv sync --extra embed`.

Results are the record, not this page. Quote figures from `docs/data/eval.json`.
