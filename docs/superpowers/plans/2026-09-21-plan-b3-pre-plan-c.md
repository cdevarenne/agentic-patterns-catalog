# Pre-Plan-C Implementation Plan (issues #1, #2, #3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three p1 issues that Plan C builds against: the `Ledger` / `PolicyDecisionPoint` / `Store.embeddings` seams (#1), a `CATALOG_ROOT` override (#2), and a measured relevance gate so `select` returns the empty message for off-topic queries (#3).

**Architecture:** Three independent tasks, each its own commit and its own issue close. #1 adds protocols plus their default implementations with no wiring into `select`; #2 is one function in `paths.py` plus an ADR; #3 adds a query-level gate to `Selector.select` whose two floors are read from `eval/thresholds.json` and justified by a generated calibration record, with off-topic cases added to the golden set and scored by `catalog eval`.

**Tech Stack:** Python 3.14, uv, pydantic v2, numpy (via rank-bm25), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-12-agentic-patterns-catalog-design.md` §2, §4.6, §5, §6.1, §9. Issues: #1, #2, #3. Decision records: `docs/adr/0001` §3/§4.6; new `docs/adr/0004-catalog-root.md` (Task 2).

## Global Constraints

- Python **3.14** via uv; `[project] dependencies` unchanged.
- Before **every** commit: `uv run --extra lint ruff check .` and `uv run pytest -q -m "not mirror"`.
- Commit messages: one-line subject, no `Co-Authored-By` or `Claude-Session` trailer.
- Every test that constructs `FileStore`, `JsonlLedger` or writes an embedding cache passes an explicit path under `tmp_path`. Nothing writes to the real `var/`.
- No numbers typed into prose or code that were not first written to a record under `docs/data/` (spec §2). Task 3's floors come from `docs/data/floor-calibration.json`.
- Published envelope shape (`hits, retrieval_path, catalog_version, auth, empty_message`) does not change.
- Work directly on `main`. Each task ends with `git push origin main` and `gh issue close <n> -c "Implemented in <sha>."`.
- Docstrings in ASD-STE100: short sentences, active voice.

## File Structure

```
src/agentic_patterns_catalog/
├── store.py       + ActivityEvent, Ledger, JsonlLedger, Store.embeddings, FileStore.embeddings  (Task 1)
├── policy.py      NEW: Decision, PolicyDecisionPoint, AllowlistPDP, role→tool table           (Task 1)
├── paths.py       ROOT honours CATALOG_ROOT                                                      (Task 2)
├── retrieval.py   query-level relevance gate; floors loaded from thresholds                     (Task 3)
├── evaluate.py    off-topic cases; offtopic_empty_rate metric                                    (Task 3)
└── calibrate.py   NEW: `catalog calibrate` → docs/data/floor-calibration.json                    (Task 3)
docs/adr/0004-catalog-root.md                                                                    (Task 2)
eval/tasks.jsonl (+10 off-topic cases), eval/thresholds.json (+2 floors, +1 rate)               (Task 3)
docs/data/floor-calibration.json (generated), docs/data/eval.json (regenerated)                 (Task 3)
tests/test_policy.py NEW; tests/test_store.py, test_paths.py NEW, test_retrieval.py, test_evaluate.py
```

---

### Task 1: Interface seams — `Ledger`, `PolicyDecisionPoint`, `Store.embeddings` (#1)

**Files:**
- Create: `src/agentic_patterns_catalog/policy.py`, `tests/test_policy.py`
- Modify: `src/agentic_patterns_catalog/store.py`, `tests/test_store.py`

**Interfaces:**
- Produces (store): `ActivityEvent` frozen dataclass `(ts: str, tool: str, subject: str, decision: str, args: dict[str, Any], hits: list[str], provenance: dict[str, Any])`; `Ledger(Protocol)` with `append(event: ActivityEvent) -> None`; `JsonlLedger(path: Path)` appending one JSON line per event; `LEDGER_PATH = ROOT / "var" / "activity.jsonl"`; `Store.embeddings(model_name: str) -> tuple[list[str], np.ndarray] | None`; `FileStore.embeddings` implemented via the existing sidecar cache.
- Produces (policy): `Decision` frozen dataclass `(allow: bool, reason: str, role: str | None)`; `PolicyDecisionPoint(Protocol)` with `decide(subject: str, tool: str, args: dict[str, Any]) -> Decision`; `READ_TOOLS`, `TOOLS_BY_ROLE`; `AllowlistPDP(access: str | None = None)` parsing `"a@x.com:curator,b@y.com:reader"` (argument, else env `CATALOG_ACCESS`, else empty) and treating subject `"stdio-local"` as `curator`.

- [ ] **Step 1: Write the failing tests**

`tests/test_policy.py`:
```python
import pytest

from agentic_patterns_catalog import policy


def test_parse_access_string() -> None:
    pdp = policy.AllowlistPDP("a@x.com:curator, b@y.com:reader")
    assert pdp.roles == {"a@x.com": "curator", "b@y.com": "reader"}


def test_malformed_access_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="CATALOG_ACCESS"):
        policy.AllowlistPDP("a@x.com")
    with pytest.raises(ValueError, match="role"):
        policy.AllowlistPDP("a@x.com:admin")


def test_env_is_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALOG_ACCESS", "c@z.com:reader")
    assert policy.AllowlistPDP().roles == {"c@z.com": "reader"}
    monkeypatch.delenv("CATALOG_ACCESS")
    assert policy.AllowlistPDP().roles == {}


@pytest.mark.parametrize(
    ("subject", "tool", "allow"),
    [
        ("stdio-local", "put_pattern", True),
        ("a@x.com", "put_pattern", True),
        ("b@y.com", "put_pattern", False),
        ("b@y.com", "select", True),
        ("nobody@x.com", "select", False),
        ("a@x.com", "drop_everything", False),
    ],
)
def test_decide_matrix(subject: str, tool: str, allow: bool) -> None:
    pdp = policy.AllowlistPDP("a@x.com:curator,b@y.com:reader")
    d = pdp.decide(subject, tool, {})
    assert d.allow is allow
    assert d.reason


def test_decision_names_the_role() -> None:
    d = policy.AllowlistPDP("a@x.com:curator").decide("a@x.com", "select", {})
    assert d.role == "curator"
    assert policy.AllowlistPDP().decide("x@x.com", "select", {}).role is None
```

Append to `tests/test_store.py`:
```python
def test_jsonl_ledger_appends_one_line_per_event(tmp_path: Path) -> None:
    ledger = store.JsonlLedger(tmp_path / "activity.jsonl")
    e = store.ActivityEvent(ts="2026-09-21T10:00:00Z", tool="select", subject="stdio-local", decision="allow",
                            args={"task": "route"}, hits=["a-pat"], provenance={"catalog_version": "abc"})
    ledger.append(e)
    ledger.append(e)
    lines = (tmp_path / "activity.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["tool"] == "select"
    assert json.loads(lines[0])["hits"] == ["a-pat"]


def test_filestore_embeddings_is_none_without_a_cache(tmp_path: Path) -> None:
    s = store.FileStore(tmp_path / "catalog", tmp_path / "cache", embeddings_dir=tmp_path / "emb")
    s.put(_p("a-pat"))
    assert s.embeddings("hash-bow-256") is None


def test_filestore_embeddings_returns_ids_and_matrix_from_the_cache(tmp_path: Path) -> None:
    from agentic_patterns_catalog import retrieval
    s = store.FileStore(tmp_path / "catalog", tmp_path / "cache", embeddings_dir=tmp_path / "emb")
    s.put(_p("a-pat"))
    s.put(_p("b-pat"))
    retrieval.build_embedding_cache(s.all(), retrieval.HashEmbedder(), tmp_path / "emb")
    got = s.embeddings("hash-bow-256")
    assert got is not None
    ids, matrix = got
    assert ids == ["a-pat", "b-pat"] and matrix.shape == (2, 256)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_policy.py tests/test_store.py -q -k "policy or ledger or embeddings"`
Expected: `ModuleNotFoundError: agentic_patterns_catalog.policy`; `AttributeError: JsonlLedger`.

- [ ] **Step 3: Implement `policy.py`**

```python
"""Authorization decision point. `AllowlistPDP` is the default; `OpaPDP` arrives with the policy layer."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

READ_TOOLS = frozenset({"list_categories", "search_patterns", "get_pattern", "get_example", "select"})
TOOLS_BY_ROLE: dict[str, frozenset[str]] = {
    "reader": READ_TOOLS,
    "curator": READ_TOOLS | {"put_pattern"},
}
LOCAL_SUBJECT = "stdio-local"


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str
    role: str | None


class PolicyDecisionPoint(Protocol):
    def decide(self, subject: str, tool: str, args: dict[str, Any]) -> Decision: ...


def parse_access(access: str) -> dict[str, str]:
    """`"a@x.com:curator,b@y.com:reader"` → `{subject: role}`. Empty string → `{}`."""
    roles: dict[str, str] = {}
    for entry in filter(None, (e.strip() for e in access.split(","))):
        subject, sep, role = entry.partition(":")
        if not sep or not subject or not role:
            raise ValueError(f"CATALOG_ACCESS entry {entry!r} is not SUBJECT:ROLE")
        if role not in TOOLS_BY_ROLE:
            raise ValueError(f"unknown role {role!r} for {subject!r}; known: {', '.join(sorted(TOOLS_BY_ROLE))}")
        roles[subject] = role
    return roles


class AllowlistPDP:
    """Subject → role from an access string (argument, else `CATALOG_ACCESS`). Local stdio is a curator."""

    def __init__(self, access: str | None = None) -> None:
        self.roles = parse_access(access if access is not None else os.environ.get("CATALOG_ACCESS", ""))

    def decide(self, subject: str, tool: str, args: dict[str, Any]) -> Decision:
        role = "curator" if subject == LOCAL_SUBJECT else self.roles.get(subject)
        if role is None:
            return Decision(False, f"{subject!r} is not in the allowlist", None)
        if tool not in TOOLS_BY_ROLE[role]:
            return Decision(False, f"role {role!r} may not call {tool!r}", role)
        return Decision(True, f"role {role!r} may call {tool!r}", role)
```

- [ ] **Step 4: Implement the store additions**

In `store.py`: import `numpy as np` (already a transitive dependency), `dataclass`, and add after the imports:

```python
LEDGER_PATH = ROOT / "var" / "activity.jsonl"
Embeddings = tuple[list[str], np.ndarray]


@dataclass(frozen=True)
class ActivityEvent:
    """One tool call as the ledger records it. `decision` is allow or deny; a denied call has no hits."""
    ts: str
    tool: str
    subject: str
    decision: str
    args: dict[str, Any]
    hits: list[str]
    provenance: dict[str, Any]


class Ledger(Protocol):
    def append(self, event: ActivityEvent) -> None: ...


class JsonlLedger:
    """Append-only JSON lines. The default ledger; Postgres arrives with the persistence layer."""

    def __init__(self, path: Path = LEDGER_PATH) -> None:
        self.path = path

    def append(self, event: ActivityEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n")
```

Extend the `Store` protocol with:
```python
    def embeddings(self, model_name: str) -> Embeddings | None:
        """Cached vectors for every record in id order, or None when no valid cache exists."""
        ...
```

`FileStore.__init__` gains `embeddings_dir: Path = EMBEDDINGS_DIR` (import from `.paths`), stored as `self.embeddings_dir`; add:
```python
    def embeddings(self, model_name: str) -> Embeddings | None:
        from .retrieval import load_embedding_cache  # local import: retrieval imports this module

        patterns = self.all()
        matrix = load_embedding_cache(patterns, model_name, self.embeddings_dir)
        return None if matrix is None else ([p.id for p in patterns], matrix)
```

- [ ] **Step 5: Run the suite, ruff, commit, close**

Run: `uv run pytest -q -m "not mirror" && uv run --extra lint ruff check .`

```bash
git add -A
git commit -m "Define the Ledger, PolicyDecisionPoint and Store.embeddings seams"
git push origin main
gh issue close 1 -c "Implemented in $(git rev-parse --short HEAD). Protocols plus default implementations (JsonlLedger, AllowlistPDP, FileStore.embeddings); no wiring into select yet — Plan C's server does that."
```

---

### Task 2: `CATALOG_ROOT` override (#2)

**Files:**
- Modify: `src/agentic_patterns_catalog/paths.py`, `README.md`
- Create: `tests/test_paths.py`, `docs/adr/0004-catalog-root.md`

**Interfaces:**
- Produces: `paths.repo_root() -> Path` — `CATALOG_ROOT` when set (expanded, resolved, must exist and hold `catalog/`), else the in-tree default; `paths.ROOT = repo_root()`; every other constant derives from `ROOT` as today.

- [ ] **Step 1: Write the failing tests**

`tests/test_paths.py`:
```python
import importlib
from pathlib import Path

import pytest

from agentic_patterns_catalog import paths


def test_default_root_is_the_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CATALOG_ROOT", raising=False)
    assert paths.repo_root() == Path(paths.__file__).resolve().parents[2]


def test_env_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "catalog").mkdir()
    monkeypatch.setenv("CATALOG_ROOT", str(tmp_path))
    assert paths.repo_root() == tmp_path.resolve()
    importlib.reload(paths)
    assert paths.CATALOG_DIR == tmp_path.resolve() / "catalog"
    monkeypatch.delenv("CATALOG_ROOT")
    importlib.reload(paths)  # restore the module for the rest of the suite


def test_override_must_point_at_a_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CATALOG_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="catalog/"):
        paths.repo_root()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_paths.py -q`
Expected: `AttributeError: module 'agentic_patterns_catalog.paths' has no attribute 'repo_root'`.

- [ ] **Step 3: Implement**

Replace the top of `paths.py`:
```python
"""Repository-relative paths. `CATALOG_ROOT` overrides the in-tree default (ADR-0004)."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """`$CATALOG_ROOT` when set, else the checkout this package lives in. The override must hold `catalog/`."""
    override = os.environ.get("CATALOG_ROOT")
    if not override:
        return Path(__file__).resolve().parents[2]
    root = Path(override).expanduser().resolve()
    if not (root / "catalog").is_dir():
        raise FileNotFoundError(f"CATALOG_ROOT={override!r} has no catalog/ directory")
    return root


ROOT = repo_root()
```
Leave every other constant as it is.

- [ ] **Step 4: ADR and README**

`docs/adr/0004-catalog-root.md`:
```markdown
# ADR-0004 — The catalog is an in-tree tool with a `CATALOG_ROOT` override

Date: 2026-09-21
Status: Accepted. Closes issue #2.

## Context
`paths.ROOT` was `Path(__file__).resolve().parents[2]`. That is correct for an editable install
inside the checkout and wrong everywhere else: a wheel install resolves it to `site-packages`, and a
server started from another working directory cannot find `catalog/`, `schema/` or `eval/`.

## Decision
The package stays an in-tree tool: its data (`catalog/`, `schema/`, `eval/`, `var/`) lives beside
the source, not inside the package. `CATALOG_ROOT`, when set, names the checkout to use; it must
contain `catalog/`. No `importlib.resources` packaging of the data.

## Why
The data is the product and changes on its own cadence; the code is a thin tool over it. Moving
288 records, the vocabulary and the eval set into the wheel would make every enrichment a release.
An environment variable is enough for Plan C's server and for any script that imports the package
from elsewhere. If the catalog is ever consumed as a library by other projects, revisit with a
data package separate from the tool package.

## Consequences
- `paths.repo_root()` is the one place that decides; every other path derives from it.
- A wrong `CATALOG_ROOT` fails at import with a message naming the variable.
- Plan C documents `CATALOG_ROOT` in the server's start-up notes.
```

README: under Quick start, add one line: ``Running from another directory: `CATALOG_ROOT=/path/to/checkout uv run catalog verify` (ADR-0004).``

- [ ] **Step 5: Run, ruff, commit, close**

Run: `uv run pytest -q -m "not mirror" && uv run --extra lint ruff check . && CATALOG_ROOT=$PWD uv run catalog verify --skip compiled | head -3`

```bash
git add -A
git commit -m "CATALOG_ROOT overrides the in-tree root (ADR-0004)"
git push origin main
gh issue close 2 -c "Implemented in $(git rev-parse --short HEAD). See docs/adr/0004-catalog-root.md."
```

---

### Task 3: Relevance gate for `select` (#3)

**Files:**
- Create: `src/agentic_patterns_catalog/calibrate.py`, `docs/data/floor-calibration.json` (generated)
- Modify: `src/agentic_patterns_catalog/retrieval.py`, `src/agentic_patterns_catalog/evaluate.py`, `src/agentic_patterns_catalog/commands.py`, `eval/tasks.jsonl`, `eval/thresholds.json`, `docs/data/eval.json` (regenerated), `tests/test_retrieval.py`, `tests/test_evaluate.py`

**Design (measured 2026-09-21 on the current catalog, bge-small; the numbers are re-derived by `catalog calibrate`, never trusted from this text):**
- Per-hit cosine floors cannot separate: off-topic queries reach 0.634 while true hits go down to 0.539.
- A **query-level gate** does: on 28 on-topic golden cases the *top* BM25 score is ≥ 9.35; on 10 off-topic probes it is ≤ 7.72. A query passes when `top_bm25 >= query_floor_bm25` **or** `top_semantic >= query_floor_semantic`; the second term keeps a query alive that has a real semantic match but little lexical overlap, and is set above every off-topic probe's top cosine (0.634). Failing both → `EMPTY_MESSAGE`, `hits == []`.
- Floors live in `eval/thresholds.json` as `query_floor_bm25` and `query_floor_semantic`; `catalog calibrate` writes the evidence to `docs/data/floor-calibration.json` and prints suggested floors (midpoints of the gaps). The committed thresholds are a decision *derived from* that record; the record says which run they came from.

**Interfaces:**
- `retrieval.Floors` dataclass `(bm25: float, semantic: float)`; `retrieval.load_floors(path=EVAL_THRESHOLDS) -> Floors` (keys `query_floor_bm25`, `query_floor_semantic`; missing keys → `Floors(0.0, 2.0)`, i.e. gate off); `Selector(..., floors: Floors | None = None)` — `None` loads from thresholds; `Selector.select` applies the gate after scoring and before fusion; `SelectResult` unchanged; `Hit` unchanged.
- `evaluate`: a case with `"expect_empty": true` scores `hit=True` iff the result has `empty_message` set; new arm metric `offtopic_empty_rate` (fraction of `expect_empty` cases that got the empty message) and `ontopic_kept_rate` (fraction of non-gap, non-empty cases with ≥1 hit); `check_thresholds` handles the key `rrf_offtopic_empty_rate`.
- `calibrate.run(store, tasks, embedder, k=10) -> dict` → `{"run": {...}, "ontopic": {"top_bm25": [..], "top_semantic": [..], "n": 28}, "offtopic": {...}, "true_hits": {"bm25": [...], "semantic": [...]}, "suggested": {"query_floor_bm25": <midpoint of max(off) and min(on)>, "query_floor_semantic": <max(off_semantic) + 0.05 rounded to 2dp>}}`; subcommand `catalog calibrate [--k N]`.

- [ ] **Step 1: Add the off-topic cases to the golden set**

Append ten lines to `eval/tasks.jsonl` (ids `t31`–`t40`), each shaped:
```json
{"id": "t31", "task": "photosynthesis in green plants", "expected_ids": [], "expected_path": "rrf", "expect_empty": true, "notes": "off-topic probe: must return the empty message"}
```
with tasks: `photosynthesis in green plants`; `how to file a tax return in france`; `sourdough starter feeding schedule`; `best hiking trails near lyon`; `symptoms of vitamin d deficiency`; `tuning a guitar by ear`; `history of the roman republic`; `how do I change a bicycle tyre`; `knitting a scarf for beginners`; `what is the boiling point of ethanol`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_retrieval.py`:
```python
def test_gate_returns_empty_when_both_floors_fail() -> None:
    sel = r.Selector(PATTERNS, embedder=r.HashEmbedder(), floors=r.Floors(bm25=1000.0, semantic=2.0))
    res = sel.select("route requests by content to a handler", k=3)
    assert res.hits == [] and res.empty_message == r.EMPTY_MESSAGE


def test_gate_passes_on_semantic_alone() -> None:
    sel = r.Selector(PATTERNS, embedder=r.HashEmbedder(), floors=r.Floors(bm25=1000.0, semantic=0.0))
    res = sel.select("route requests by content to a handler", k=3)
    assert res.hits and res.hits[0].id == "content-routing"


def test_gate_off_when_thresholds_lack_floors(tmp_path: Path) -> None:
    p = tmp_path / "thresholds.json"
    p.write_text('{"rrf_hit_at_k": 0.6}')
    floors = r.load_floors(p)
    assert floors == r.Floors(bm25=0.0, semantic=2.0)


def test_committed_floors_keep_every_ontopic_golden_case_and_block_every_offtopic_probe() -> None:
    from agentic_patterns_catalog import evaluate, store
    ids = {p.id for p in store.FileStore().all()}
    if len(ids) < 288:
        pytest.skip("needs the full local catalog")
    sel = r.Selector.from_store(store.FileStore(), embedder=None)  # BM25 arm alone must already separate
    for t in evaluate.load_tasks():
        if t.get("gap"):
            continue
        res = sel.select(t["task"], k=5)
        if t.get("expect_empty"):
            assert res.empty_message == r.EMPTY_MESSAGE, t["id"]
        else:
            assert res.hits, t["id"]
```
(`Path` is already imported in that test file; add `import pytest` if missing.)

Append to `tests/test_evaluate.py`:
```python
def test_expect_empty_case_scores_hit_only_on_the_empty_message() -> None:
    tasks = [
        {"id": "on", "task": "route by content", "expected_ids": ["content-routing"], "expected_path": "rrf"},
        {"id": "off", "task": "zzz qqq", "expected_ids": [], "expected_path": "rrf", "expect_empty": True},
    ]
    rep = evaluate.run_eval(STORE, tasks, None, k=2)
    arm = rep["arms"]["bm25"]
    by_id = {c["id"]: c for c in arm["cases"]}
    assert by_id["on"]["hit"] is True
    assert by_id["off"]["hit"] is True          # no lexical overlap → empty message → correct
    assert arm["offtopic_empty_rate"] == 1.0
    assert arm["ontopic_kept_rate"] == 1.0
    assert rep["run"]["offtopic"] == 1


def test_threshold_key_for_offtopic_rate() -> None:
    rep = evaluate.run_eval(STORE, TASKS, None, k=2)
    assert evaluate.check_thresholds(rep, {"rrf_offtopic_empty_rate": 1.0}) == [] or \
        "rrf_offtopic_empty_rate" in evaluate.check_thresholds(rep, {"rrf_offtopic_empty_rate": 1.0})[0]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_retrieval.py tests/test_evaluate.py -q -k "gate or floors or expect_empty or offtopic"`
Expected: `AttributeError: module has no attribute 'Floors'`; `KeyError: 'offtopic_empty_rate'`.

- [ ] **Step 4: Implement the gate in `retrieval.py`**

Add near the constants:
```python
@dataclass(frozen=True)
class Floors:
    """Query-level relevance gate. A query passes when its best BM25 score reaches `bm25`
    or its best cosine reaches `semantic`; otherwise `select` returns the empty message."""
    bm25: float
    semantic: float


GATE_OFF = Floors(bm25=0.0, semantic=2.0)  # cosine never reaches 2.0, BM25 always reaches 0.0


def load_floors(path: Path = EVAL_THRESHOLDS) -> Floors:
    """Floors from thresholds.json; missing keys switch the gate off (the pre-calibration behaviour)."""
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if "query_floor_bm25" not in data or "query_floor_semantic" not in data:
        return GATE_OFF
    return Floors(bm25=float(data["query_floor_bm25"]), semantic=float(data["query_floor_semantic"]))
```
Import `EVAL_THRESHOLDS` from `.paths` and `dataclass` if not already. `Selector.__init__` gains `floors: Floors | None = None` → `self.floors = floors if floors is not None else load_floors()`.

In `Selector.select`, after both arms have scored and **before** `fused = rrf(...)`:
```python
        top_bm = max(bm_scores.values(), default=0.0)
        top_sem = max(sem_scores.values(), default=-1.0)
        if top_bm < self.floors.bm25 and top_sem < self.floors.semantic:
            return SelectResult([], path, self.version, auth, EMPTY_MESSAGE)
```
Note the BM25 arm already drops zero scores, so `top_bm` is 0.0 when nothing overlaps; with `GATE_OFF` (`bm25=0.0`) the condition `0.0 < 0.0` is False and behaviour is unchanged.

- [ ] **Step 5: Implement `calibrate.py`**

```python
"""Measure the scores that justify the relevance gate, and write the record the floors are derived from."""
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
from .retrieval import GATE_OFF, Embedder, Selector, default_embedder
from .store import FileStore, Store, content_version, git_ref


def _summary(xs: list[float]) -> dict[str, float | int]:
    return {"n": len(xs), "min": min(xs, default=0.0), "median": statistics.median(xs) if xs else 0.0,
            "max": max(xs, default=0.0)}


def run(store: Store, tasks: list[dict[str, Any]], embedder: Embedder | None, k: int = 10) -> dict[str, Any]:
    """Top scores per on-topic and off-topic query, true-hit scores, and the floors they suggest."""
    patterns = store.all()
    selector = Selector(patterns, embedder, floors=GATE_OFF)  # measure with the gate off
    on_bm, on_sem, off_bm, off_sem, hit_bm, hit_sem = [], [], [], [], [], []
    for t in tasks:
        if t.get("gap"):
            continue
        res = selector.select(t["task"], t.get("facets"), k)
        tb = max((h.score_bm25 or 0.0) for h in res.hits) if res.hits else 0.0
        ts = max((h.score_semantic or 0.0) for h in res.hits) if res.hits else 0.0
        if t.get("expect_empty"):
            off_bm.append(tb)
            off_sem.append(ts)
            continue
        on_bm.append(tb)
        on_sem.append(ts)
        for h in res.hits:
            if h.id in t["expected_ids"]:
                if h.score_bm25 is not None:
                    hit_bm.append(h.score_bm25)
                if h.score_semantic is not None:
                    hit_sem.append(h.score_semantic)
    suggested = {
        "query_floor_bm25": round((max(off_bm, default=0.0) + min(on_bm, default=0.0)) / 2, 2),
        "query_floor_semantic": round(max(off_sem, default=0.0) + 0.05, 2),
    }
    return {
        "run": {"catalog_version": content_version(patterns), "git_ref": git_ref(),
                "embed_model": embedder.name if embedder else None,
                "date": dt.datetime.now(dt.UTC).date().isoformat(), "k": k},
        "ontopic": {"top_bm25": _summary(on_bm), "top_semantic": _summary(on_sem)},
        "offtopic": {"top_bm25": _summary(off_bm), "top_semantic": _summary(off_sem)},
        "true_hits": {"bm25": _summary(hit_bm), "semantic": _summary(hit_sem)},
        "separable": {"bm25": max(off_bm, default=0.0) < min(on_bm, default=0.0),
                      "semantic": max(off_sem, default=0.0) < min(on_sem, default=0.0)},
        "suggested": suggested,
    }


def write(report: dict[str, Any], path: Path = DATA_DIR / "floor-calibration.json") -> Path:
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
        print(json.dumps({"separable": report["separable"], "suggested": report["suggested"]}))
        print(f"wrote {path}")
        return 0
    return run_cmd
```
Add `from . import calibrate  # noqa: F401` to `commands.py`. Test (append to `tests/test_evaluate.py`): `calibrate.run(STORE, TASKS + [off-topic case], r.HashEmbedder(), k=2)` returns the four sections and `suggested` has both keys.

- [ ] **Step 6: Implement the eval changes**

In `evaluate._score_arm`, per case:
```python
        res = selector.select(t["task"], t.get("facets"), k)
        top = [h.id for h in res.hits]
        if t.get("expect_empty"):
            hit, rr = res.empty_message is not None, 0.0
        else:
            ranks = [top.index(e) + 1 for e in t["expected_ids"] if e in top]
            hit, rr = bool(ranks), (1.0 / min(ranks) if ranks else 0.0)
```
and compute, besides `hit_at_k`/`mrr` (over on-topic cases only), `offtopic_empty_rate` = mean of `hit` over `expect_empty` cases (1.0 when there are none) and `ontopic_kept_rate` = fraction of on-topic cases with a non-empty `top`. `run_eval`'s `run` block gains `"offtopic": <count>`. `check_thresholds` already splits on the first `_`, so `rrf_offtopic_empty_rate` works unchanged.

- [ ] **Step 7: Calibrate, set the floors, regenerate, prove separation**

```bash
uv run catalog calibrate
```
Read `docs/data/floor-calibration.json`. Both `separable` flags must be true for the gate design to hold on this data; if `semantic` is false that is expected (documented above) and only `bm25` needs to be true. Copy `suggested.query_floor_bm25` and `suggested.query_floor_semantic` into `eval/thresholds.json`, and add `"rrf_offtopic_empty_rate": 1.0`. Then:
```bash
uv run catalog eval
uv run pytest tests/test_retrieval.py -q -k committed_floors
```
Expected: `eval` prints `offtopic_empty_rate=1.000` for every arm and the on-topic `hit@5` values unchanged from the previous record (0.750 rrf) — if `ontopic_kept_rate` < 1.0 the floors are too high: stop and report the case ids, do not lower the numbers by hand.

- [ ] **Step 8: Docs**

`docs/eval-how-to.md`: one paragraph — the gate, the two floors, that `catalog calibrate` regenerates the evidence and `eval/thresholds.json` holds the decision; quote no numbers, point at `docs/data/floor-calibration.json`. Spec §5: after step 4 (RRF) insert "5. Query gate: if the best BM25 score is below `query_floor_bm25` **and** the best cosine is below `query_floor_semantic` (both in `eval/thresholds.json`, derived from `docs/data/floor-calibration.json`), the result is the empty message. Per-hit floors were measured and rejected: cosine baselines overlap." Renumber the following step.

- [ ] **Step 9: Full gate, commit, close**

Run: `uv run --extra lint ruff check . && uv run pytest -q && uv run catalog verify`
Expected: all green; `verify`'s `eval` check reads the regenerated record and the new threshold.

```bash
git add -A
git commit -m "select gates off-topic queries on measured BM25 and cosine floors"
git push origin main
gh issue close 3 -c "Implemented in $(git rev-parse --short HEAD). Floors in eval/thresholds.json, evidence in docs/data/floor-calibration.json, ten off-topic probes in the golden set scored by catalog eval."
```

---

## Self-review against the spec and issues

- #1 asks for `Ledger`, `PolicyDecisionPoint`, `Store.embeddings` — Task 1 defines all three with default implementations and tests; no `select` wiring (issue text: "with no behaviour change"). `Store.embeddings` returns `(ids, matrix)`; the reviewer's `nearest(vec, k)` alternative is left for Plan C's Postgres design, noted in the close comment. ✔
- #2 asks for the override and a recorded packaging decision — Task 2, ADR-0004. ✔
- #3 asks for floors chosen from data, off-topic cases in the golden set, floors applied and recorded — Task 3; the design departs from the issue's implicit per-hit floor because measurement showed it cannot work, and says so in spec §5. ✔
- Spec §2 "empty result never fills the gap" — Task 3 restores it for off-topic queries; spec §2 "numbers generated, never typed" — floors trace to `floor-calibration.json`. ✔
- Type consistency: `Floors`, `load_floors`, `GATE_OFF` used identically in retrieval, calibrate and tests; `Selector(patterns, embedder, floors=)` keyword in both. `ActivityEvent` field order matches the test. ✔
- Placeholder scan: Task 3 step 7 deliberately does not type the floor values; they are read from the generated record. ✔
