# How to run the evaluation

`uv run catalog eval` runs `eval/tasks.jsonl` through three arms of `select` (BM25, semantic, RRF)
and writes `docs/data/eval.json`. `eval/thresholds.json` names the floors `catalog verify` enforces.
The semantic arm needs the `embed` extra: `uv sync --extra embed`.

The golden set also holds off-topic probes (`expect_empty: true`). `select` answers them with the
empty message through a query gate: a combined score of the best BM25 score and the best cosine,
compared with `query_gate_threshold` in `eval/gate.json`. `uv run catalog calibrate` regenerates
the evidence for that threshold into `docs/data/floor-calibration.json` (per-signal summaries, the
`separable` flags, the `relevance` gap) and prints the suggested value; `eval/gate.json` holds the
decision and names the record it came from. The gate runs only when both arms run, so
`offtopic_empty_rate` is meaningful for the `rrf` arm alone; the `bm25` and `semantic` arms report
their honest, low rates. Without the `embed` extra `select` cannot detect off-topic queries; it
returns its best lexical matches with their scores.

Results are the record, not this page. Quote figures from `docs/data/eval.json`.
