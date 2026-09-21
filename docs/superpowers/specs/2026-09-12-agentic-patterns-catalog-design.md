# Spec — Agentic Patterns Catalog (SP1)

Date: 2026-09-12
Status: approved design, awaiting implementation plan
Decision record: `docs/adr/0001-catalog-design.md` (the reviewed brainstorm, with every reviewer
decision). This spec applies those decisions. Where the two disagree, this spec is wrong; fix it.
Diagram: `docs/architecture.mmd`.

## 1. What this is

A catalog of 288 agentic design patterns (24 categories), structured so an agent can be given a
task and receive the two to five patterns that apply, with enough context to apply them and with
provenance for every field. Primary consumers: a Claude Code skill and a runtime `select` tool
reached over MCP by a Python (LangGraph) agent and a Kotlin (Embabel) agent.

This is sub-project 1 (SP1) of a larger program: a Spring-Integration-style platform in which the
catalog is the component registry, a *recipe* is the flow DSL, and a composer builds agent systems
from a use-case description, then runs them through a Build-Measure-Learn loop. SP2–SP9 are listed
in §12 and are out of scope here except for the seams SP1 must leave for them.

## 2. Design properties

Every decision serves: **useful, secure, repeatable, composable, deterministic-where-it-matters.**
Concretely:

- The deterministic path (`get_pattern` by id, facet filter, BM25) runs on a bare install with no
  cloud, no key, no database. Embeddings, Postgres, OAuth and OPA are extras.
- Every answer carries provenance. No answer without it. An empty result says
  `"No pattern matches in the catalog."` and never fills the gap.
- Published numbers are generated, never typed. `docs/data/*.json` holds results; prose cites them.
- One command verifies everything: `uv run catalog verify`.
- Write documents, docstrings, comments and commit messages in ASD-STE100 Simplified Technical
  English: short sentences, one idea per sentence, active voice, simple present tense.

## 3. Inputs and their licenses

| Input | Location | Fields | License / use |
|---|---|---|---|
| Site mirror, raw pages | `../agentic-design-mirror/pages/raw/patterns/**` | Next.js RSC payload (`self.__next_f.push`) with the pattern object | © KORTEXYA; personal education only. Per ADR-0003, the tracked record for these 277 patterns is identity + `selection` + `provenance`; the extracted `content.*` is a **gitignored** cache under `var/content/` rebuilt locally by `catalog extract`. |
| Free pack | `../agentic-design-mirror/patterns-pack-free/data/patterns.json` | 11 tool-use records: `id, name, category, categoryName, complexity, description, features, useCases, tldr, example, code, references` | "Free to use in your own projects … do not republish as your own." The 11 tracked records carry no `content`, like the other 277 (ADR-0003); their licensed prose is tracked in `data/pack/patterns.json` (pack README quoted) and `catalog seed` caches it under `var/content/`. |
| Free pack MCP server | `…/patterns-pack-free/mcp-server/server.mjs` | tool names and shapes | Reused as naming precedent only (cited); no code copied. |
| Free pack Markdown sheets | `…/patterns-pack-free/markdown/tool-use/*.md` | sheet layout | Layout reused for compiled reference sheets (cited). |

Measured 2026-09-12 by parsing the raw pages (prototype in the plan): every page carries two
sources of pattern content. Both are site prose. No tracked record carries `content`; only the 11
pack records' prose is tracked, in `data/pack/patterns.json`. Category records (§4.2b) stay
gitignored, since their prose is not licensed for redistribution.

1. The RSC props (JSON): the pattern object (`id, name, abbr, category, complexity, description,
   example, features, useCases, references`) plus page-level `tldr{what, when, watchOut}`,
   `codeExamples{typescript, python, rust}` and `flowScenario{title, description, initialNodes,
   initialEdges, steps}`; and all 24 category objects (`id, name, description, detailedDescription,
   whyImportant, implementationGuide{whenToUse, bestPractices, commonPitfalls}, techniques[]`).
   `whenToUse / bestPractices / commonPitfalls` are **category-level**, not pattern-level.
2. A streamed HTML block (`<div hidden id="S:3">…`) with per-pattern detail sections in one of three
   templates (counts measured by the extractor on 2026-09-12): *deep* (35 pages: Core Mechanism,
   Workflow / Steps, Best Practices, When NOT to Use, Common Pitfalls, Key Features, KPIs / Success
   Metrics, Token / Resource Usage, Best Use Cases), *standard* (161 pages: 30-Second Overview, Quick
   Implementation, Do's & Don'ts, When to Use, Key Metrics, Top Use Cases), or *prose-only* (92 pages:
   a title and one paragraph, no sections — `content.details` is empty for these). The extractor
   parses the block with `beautifulsoup4` (MIT) into `content.details`, keyed by normalized heading,
   so every template fits one shape.

## 4. Data model

### 4.1 Pattern record

One file per pattern: `catalog/patterns/<category>/<slug>.json`. Pydantic v2 models in
`src/agentic_patterns_catalog/model.py` are the source of truth; `schema/pattern.schema.json`
(JSON Schema 2020-12) is generated from them and a test asserts the committed file equals a fresh
generation.

```
id            "<slug>"                         stable key; equals the pack id; unique across all 288 (measured);
                                               `^[a-z0-9]+(-[a-z0-9]+)*$` (also `category` and `Category.id`) — the id is a path segment
name, category, kind, complexity
  kind        pattern | technique | benchmark | tool      (SP4+ sections add values; closed enum)
content       description, abbr, tldr{what, when, watchOut}, features[], useCases[], example,
              code{typescript, python, rust}, references[],
              flow{title, description, nodes[], edges[], steps[]},
              details{<normalized heading>: [str]}     e.g. core_mechanism, workflow_steps,
                                                       when_not_to_use, quick_implementation …
              — field names identical to the pack's patterns.json where the pack has the field;
                all optional except description and tldr
selection     problem_signals[], preconditions[], contraindications[],
              facets{scale, latency_cost, token_cost, risk_class, maturity}      closed enums, see 4.2
              relations[{type, target, prefer_when}]
                type ∈ alternative_to | composes_with | requires | precedes
provenance    source{url, mirrored_at, extraction ∈ rsc-payload | free-pack, content_sha256}
              enrichment{<selection field>: {method ∈ llm-draft | human | derived,
                                              model, date, reviewed_by | null}}
```

### 4.2 Facet vocabulary (controlled; one authority, three projections)

The vocabulary lives in one data file, `catalog/vocab/facets.json`
(`{"scale": ["single-agent", …], …}`). The pydantic `Literal` types are generated from it, the
Postgres `CHECK` constraints in `PostgresStore` are derived from it, and the rego role/facet data
is exported from it. Adding a value is a data change plus review, not a code change; the schema
test fails until `schema/pattern.schema.json` is regenerated, which is the intended friction.
Unknown values are errors: the `Facets` model validates every value against the vocabulary file
when a record is loaded or written, and `catalog verify` fails on them. `verify --lenient-vocab`
downgrades them to warnings for a vocabulary-discovery session only. Initial values:

| Facet | Values |
|---|---|
| `scale` | single-agent, multi-agent, fleet |
| `latency_cost` | none, adds-1-llm-call, adds-n-llm-calls, async-only |
| `token_cost` | low, medium, high |
| `risk_class` | misroute, data-leak, unsafe-action, cost-runaway, quality-drift, none |
| `maturity` | research, emerging, production |

### 4.2b Category record

`catalog/categories/<id>.json`, model `Category`: `id, name, description, detailedDescription,
whyImportant, implementationGuide{whenToUse[], bestPractices[], commonPitfalls[]}, technique_ids[]`
(ids of the patterns listed under `techniques`), `provenance{source}` (same shape as `Pattern`).
Category `description`, `detailedDescription`, `whyImportant` and `implementationGuide` are site
prose: the free pack licenses only the `tool-use` category line. Category records are therefore
**gitignored like the content cache** and rebuilt by `catalog extract`. Committed compiled
views quote a category's `id` and `name` only (the taxonomy); `compile --local` adds the
description and the `implementationGuide` sections to the local guides.

### 4.2c Tracked record vs content cache (ADR-0003)

[ADR-0003](../../adr/0003-enrichment-is-the-tracked-record.md) decides that the tracked record is
identity + `selection` + `provenance` for all 288 patterns, and that site `content` is a
gitignored cache rebuilt by `catalog extract` (and by `catalog seed` from `data/pack/patterns.json`
for the 11 free-pack records). `Pattern.content` is optional and `FileStore` merges the cache at
load.

### 4.3 Index

`catalog/index.json`: for every record `id, kind, category, content_sha256, enrichment.reviewed`
(true when every `selection` field has `reviewed_by`). This is the freshness and coverage ledger.

### 4.4 Relations as a graph

Edges live on the source record. `catalog compile` builds the graph, fails when a `target` does
not resolve, and fails when `precedes` has a cycle. No global decision tree is stored; a tree is a
frozen tag filter and goes stale when a record is added. Per-category `GUIDE.md` files are compiled
from facets and `alternative_to` + `prefer_when`.

### 4.5 Recipe (the SP4 seam, minimal in SP1)

`catalog/recipes/<slug>.json`, schema `schema/recipe.schema.json`:

```
id, name, use_case (one paragraph), steps[{order, pattern_id, role, binding_notes}],
source_documents[], provenance{method, date, reviewed_by}
```

SP1 ships one recipe, authored by hand from the documents named in ADR-0001 §2 response:

- `drone-flight-plan`: knowledge grounding → plan generation → validate against rules → SORA risk
  score → document → human sign-off. Source: `drone_flightplan_usecase (1).md` §1 and §3,
  `drone_sora_hazards_bundle.md`.

**Removed 2026-09-15 — the Co-Scientist digital-lab recipe.** The original plan carried a second
recipe that generated, debated, ranked and evolved research hypotheses. Kirgis, Kapoor, Schwartz et
al., "Can AI agents conduct open-ended AI research? Early evidence from two case studies"
(arXiv:2607.27191, 2026-08-07) ran shadow evaluations in which well-resourced frontier agents were
given the central research question of an unpublished paper, six days and thousands of dollars of
compute. Both outputs were unambiguously rejected by the papers' own authors, with five recurring
failure modes: poor judgment about the bar for publishable research, uncreative response to
shortcomings, ineffective backtracking from dead ends, poor resource awareness, and instruction
drift. A reference instance whose value depends on the capability that evidence says is absent would
demonstrate the catalog on a task it cannot pass. The drone flight plan is the opposite shape — a
bounded, rule-grounded, verifiable task with a human sign-off gate — so it stays. The agent patterns
the removed recipe exercised (supervisor orchestration, reflection, meta-review, asynchronous task
queues, context memory) remain in the catalog and remain covered by the golden set; only the
end-to-end research-lab use case is withdrawn. Revisit when comparable evidence changes.

Every `pattern_id` must resolve; `verify` checks it. A recipe whose step names a pattern the catalog
lacks is a documented coverage gap, not an invented pattern.

### 4.6 Persistence — `Store` and `Ledger` interfaces (the SP2 seam)

```python
class Store(Protocol):
    def get(self, id: str) -> Pattern: ...
    def all(self) -> Iterable[Pattern]: ...
    def put(self, p: Pattern) -> None: ...           # curator only
    def embeddings(self) -> Embeddings | None: ...   # None when the embed extra is absent

class Ledger(Protocol):
    def append(self, event: ActivityEvent) -> None:  # tool, subject, args, hit ids, provenance, ts
```

- `FileStore` + `JsonlLedger` (`var/activity.jsonl`) — default; no extra.
- `PostgresStore` + `PostgresLedger` — extra `pg`; PostgreSQL 18 with pgvector 0.8.6 (verified
  installed locally). Tables: `pattern(id pk, doc jsonb, content_sha256, updated_at)`,
  `pattern_embedding(id fk, model, vec vector(n))`, `activity(id, ts, tool, subject, args jsonb,
  hits text[], provenance jsonb)`. Records are loaded from files with `catalog sync-pg`; Postgres
  is a mirror, never the source of truth in SP1.
- The Python agent uses `langgraph-checkpoint-postgres` when `pg` is present; in-memory otherwise.
- `verify` runs its store checks against every configured store.

## 5. Retrieval — `select`

`select(task: str, facets: dict | None, k: int = 5) -> SelectResult`

0. Validate: `k >= 1`; every facet name is in `FACET_NAMES` and every value is in the vocabulary,
   else `ValueError` (the CLI maps it to a usage error). An unknown facet is never an empty result.
1. Facet pre-filter (exact match on declared facets; absent facet = no filter).
2. BM25 over `name + tldr.* + problem_signals + useCases + whenToUse` (`rank_bm25`, MIT).
3. Semantic arm over the same text with `fastembed` (Apache-2.0, local ONNX); skipped when the
   `embed` extra is absent and the result says so in `retrieval_path`.
4. Reciprocal Rank Fusion, `k_rrf = 60`; ties broken by id for determinism.
5. Query gate, active only when both arms run: `relevance = top_bm25 / BM25_SCALE +
   max(0, top_cos - COS_BASE) / COS_SCALE` (constants in `retrieval.py`); when it is below
   `query_gate_threshold` (`eval/gate.json`, derived from `docs/data/floor-calibration.json`), the
   result is the empty message. Per-signal floors were measured and rejected: the best BM25
   score alone separates the golden set by 0.03 (no usable margin) and the best cosine alone does
   not separate it (per-signal margins under `separable` in the record); the combined score does.
   The gate applies only when every record has cached content: it is calibrated on full content,
   and a store without `var/content` runs ungated (one line on stderr says so).
   Without the `embed` extra there is no semantic arm and
   `select` cannot detect off-topic queries; it returns its best lexical matches with their scores.
6. Top-k hits, each with `score_bm25, score_semantic, rrf_rank, retrieval_path
   (bm25 | semantic | rrf)`, the record's `provenance`, `reviewed`, and 1-hop `relations`.

Envelope fields (always present; `null` when not applicable, never absent):
`hits[], retrieval_path, catalog_version, auth{subject}, empty_message | null`.

`catalog_version` is content-derived: the first 12 hex digits of SHA-256 over the sorted lines
`<id>:<content_sha256>` of every record in the store. It is the same in the index, the `select`
envelope and the eval record, works in CI and outside git, and changes when — and only when — a
record's content changes. The git sha of the last commit touching `catalog/` is recorded beside it
as `git_ref` where a run block exists, for humans.

The semantic arm is optional at runtime as well as at install time: when the embedder cannot load
(no extra, no cached model and no network), `select` runs BM25 only, says so once on stderr, and the
envelope's `retrieval_path` reads `bm25`. It never fails because a model file is absent.

## 6. MCP server

FastMCP v3 (`prefecthq/fastmcp`, Apache-2.0). One server object, two transports:

| Transport | AuthN | When |
|---|---|---|
| stdio | none; `auth.subject = "stdio-local"` | dev default; `.mcp.json` entry |
| Streamable HTTP `http://localhost:8000/mcp` | `GoogleProvider(client_id, client_secret, base_url, required_scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"])`, values from env (v3 has no automatic env loading) | when `CATALOG_HTTP=1` |

Tools: `list_categories`, `search_patterns(query, category?)`, `get_pattern(id)`,
`get_example(id, language?)`, `select(task, facets?, k?)`, and for curators `put_pattern(record)`.
Names match the free pack's server so an agent prompt written for one works against the other.

### 6.1 AuthZ — `PolicyDecisionPoint` (the SP3 seam)

```python
class PolicyDecisionPoint(Protocol):
    def decide(self, subject: str, tool: str, args: dict) -> Decision:  # allow | deny + reason
```

- `AllowlistPDP` (default): `CATALOG_ACCESS="a@x.com:curator,b@y.com:reader"`; roles `reader`
  (all read tools) and `curator` (also `put_pattern`). stdio subject is `curator`.
- `OpaPDP` (extra `opa`): POST to `http://localhost:8181/v1/data/catalog/authz/decision` with
  `{input: {subject, tool, args}}`; policies in `policy/catalog/authz.rego`; `opa test policy/` in
  CI; the rego encodes the same role table so the two PDPs agree, and a test asserts that.
- Every decision, allow or deny, is appended to the `Ledger` before the tool body runs.

### 6.2 Google Cloud prerequisites (manual, documented in `docs/auth.md`)

A *Web application* OAuth client with authorized redirect `http://localhost:8000/auth/callback`.
Assumption: the existing Desktop-type client from the YouTube scripts cannot be reused; the check is
the client type in the console. Secrets live in `.env` (gitignored); `.env.example` names them.

## 7. Compiled views (L2)

`catalog compile` writes, and never hand-edits:

| Output | Content | Budget / check |
|---|---|---|
| `skills/agentic-patterns/generated/CATALOG.md` | one line per **category** (24): `- **<id>** — <name> — <n> patterns` (the description is site prose and appears only under `--local`) | token estimate (`len(text) / 4`) asserted under 2k |
| `skills/agentic-patterns/generated/CATALOG-full.md` | one line per record. Pack records: `id — tldr.what — use when: tldr.when`, from their cached `content` (`catalog seed` fills it from the tracked `data/pack/patterns.json`). The other 277 are tracked as identity + `selection` + `provenance` only (ADR-0003): `id — name — first problem_signal` when enriched, `id — name` until then, so no mirror site prose is committed. `compile --local` may use `tldr` from the local content cache for all 288, for local use and the smoke test; that output is gitignored. | token estimate asserted under 16k |
| `skills/agentic-patterns/generated/guides/<category>.md` | comparison table of the category's patterns by facets; `alternative_to` rows with `prefer_when`; the category's `implementationGuide` sections only under `--local` | every pattern of the category appears once; `compile` removes files it did not produce |
| `skills/agentic-patterns/generated/sheets/<id>.md` | full reference sheet, pack layout | only for the 11 pack records in git; all 288 locally |
| `catalog/embeddings/<model>.npy` + ids | semantic arm index | gitignored; rebuilt by compile |

`skills/agentic-patterns/SKILL.md` (hand-written) states the four-step contract: read CATALOG.md →
call `select` when the MCP server is reachable, otherwise open the category GUIDE (or
CATALOG-full.md offline) → apply the full record → check `contraindications` before committing to
a pattern.

## 8. Enrichment (L1)

- `catalog enrich --category <c>`: for each record, one Claude call with `content.*` as the only
  input and the committed prompt `prompts/enrich.md`; writes `var/review/<id>.json` with the drafted
  `selection` block and `provenance.enrichment.method = llm-draft`, `model`, `date`.
- `catalog review <id> --accept | --edit`: moves the block into the record and sets `reviewed_by`.
- Served envelopes carry `reviewed: false` for any record with an unreviewed field.
- Order: routing, workflow-orchestration, multi-agent, tool-use, memory-management,
  fault-tolerance-infrastructure, planning-execution, then the rest; `ui-ux-patterns` and
  `kind = benchmark` last.

## 9. Evaluation

- `eval/tasks.jsonl`: 30 cases `{task, expected_ids[], expected_path, notes}`. At least five come
  from the drone flight-planning use case. Seven more describe multi-agent analysis work
  (hypothesis generation, reflection, meta-review, supervisor orchestration, asynchronous queues,
  context memory); they were written for the withdrawn Co-Scientist recipe (§4.5) and are kept
  because each one still tests a real retrieval path.
- `catalog eval` runs three arms (BM25, semantic, RRF), writes `docs/data/eval.json` with a `run`
  block (`catalog_version`, embed model, date) and per-case verdicts. Prose never restates verdicts.
- Smoke test before enrichment exists: compile `CATALOG.md` from `tldr` only, run five tasks through
  an agent, record the verdicts in `docs/data/smoke.json`.

## 10. Consumers

- **Claude Code skill**: §7. Installed by symlink into `~/.claude/skills/` (documented).
- **Python agent** `agents/python/` (LangGraph, extra `agent`): nodes `select → plan → check`;
  `plan` drafts an application plan citing pattern ids; `check` rejects any cited pattern whose
  `contraindications` match the task's declared constraints and emits the provenance block.
  MCP transport: stdio by default; HTTP when `CATALOG_URL` is set.
- **Kotlin agent** `agents/kotlin/` (Embabel from `embabel/kotlin-agent-template`, JDK 21, Gradle):
  the same three steps as `@Action`s under one `@Goal`; MCP via
  `spring.ai.mcp.client.streamable-http.connections.catalog.url`. **Open verification:** whether the
  Spring AI MCP client performs the OAuth browser flow. Assumed fallback: a bearer token obtained once
  with the FastMCP Python client and passed as a header. Recorded as a risk in the plan.
- CrewAI: not used.

## 11. Verification and repository rules

- `uv run catalog verify`: every record validates (patterns, categories, recipes; a malformed file
  is reported, never a traceback); `index.json` entries equal a fresh index (all fields, and the
  category and recipe lists); relation targets resolve; `precedes` acyclic; recipe `pattern_id`s
  resolve; committed schema equals generated; no file under `generated/` that a fresh compile does
  not produce;
  `CATALOG.md` and `CATALOG-full.md` under budget; facet values in the vocabulary; compiled outputs equal a fresh compile; `eval.json` within declared
  tolerance; every configured store passes the same checks. CI and a fresh clone see all 288 records and
  no content cache; only `compiled` needs one (the pack sheets), so CI runs `verify --skip compiled`.
- `uv run --extra lint ruff check .` passes before every commit.
- Toolchain: Python 3.14, uv, `uv.lock` committed; `[project] dependencies = pydantic, rank_bm25`;
  extras `embed` (fastembed), `mcp` (fastmcp), `pg` (psycopg, pgvector, langgraph-checkpoint-postgres),
  `opa` (httpx), `agent` (langgraph), `dev` (pytest), `lint` (ruff). The plain `python3.14 -m venv`
  + `pip install -e ".[dev]"` path is kept working and documented.
- License: MIT for this repository. Attribution to agentic-design.ai in the README, in the pack's
  quoted license text, and in every record's `provenance.source.url`.
- Commits: one author; every commit ships tests, or says why it cannot (docs, tooling).

## 12. Out of scope for SP1, and the roadmap seams it leaves

| # | Sub-project | Seam SP1 provides |
|---|---|---|
| SP2 | Persistence + activity ledger (full Postgres design, checkpoint analysis, observability views) | `Store`, `Ledger`, `PostgresStore` minimal impl |
| SP3 | Policy layer (rego beyond RBAC; Conseca-style per-task policies from trusted context) | `PolicyDecisionPoint`, `OpaPDP`, `policy/` |
| SP4 | Recipe DSL (bindings, parameters, validation) | `recipe.schema.json`, two recipes |
| SP5 | Drone fleet blueprint (flight plan, SORA, PX4 SITL) | recipe `drone-flight-plan` |
| SP6 | Composer (use case → agent set) | recipes + `select` |
| SP7 | BML loop + digital twin (Airflow vs Prefect vs LangGraph decided here) | `Ledger`, `eval.json` shape |
| SP8 | Edge / cloud deploy | none in SP1 |

Also out: multi-tenant, hosted deployment, the four mirrored site sections as catalog content
(`kind` enum is ready), a Kotlin server, LLM reranking, Celery, Airflow.

## 13. Companion change in `agentic-design-mirror`

`mirror.py` gains `--section` (default `patterns`) and `--out` (default `pages`);
`pattern_urls()` becomes `section_urls(sitemap_xml, section)`. Tests cover the five sections
against a fixture sitemap and the `--out` layout. No library swap: the stdlib politeness/robots code
is tested and would gain nothing from `requests`/`protego`. Documented runs:
`ai-red-teaming → redteaming` (113 pages), `ai-inference → inference` (21),
`fine-tuning → fine-tuning` (9), `model-architectures → model-architectures` (25).

## 14. Build order (from ADR-0001 §8, with SP1 additions)

1. Mirror refactor; run the four sections. Check: tests pass; page counts match §13.
2. Models, schema, extractor, pack seed, `FileStore`. Check: 288 + 11 validate; coverage report.
3. `CATALOG.md` compiler; smoke test. Check: `smoke.json` written.
4. Selection enums, enrich `routing` end to end, first `GUIDE.md`, relations DAG check.
5. `select` (BM25 → +semantic → RRF); golden set; `catalog eval`. Check: `eval.json`.
6. MCP server stdio → HTTP + GoogleProvider → `AllowlistPDP` → `OpaPDP`; `Ledger`. Check: PDP
   parity test; denied/allowed cases with a fake token verifier; one manual login documented.
7. `PostgresStore`/`PostgresLedger` + `sync-pg`; `verify` against both stores.
8. Skill; Python agent; Kotlin agent. Check: same hits + provenance on the golden tasks.
9. One recipe (`drone-flight-plan`); recipe checks in `verify`; recipe-derived eval cases.
10. Enrichment across priority categories; CI.

Parallel tracks once step 2 lands: SP2's fuller design and SP3's rego learning can proceed against
the `Store`/`PolicyDecisionPoint` interfaces without blocking steps 3–5.
