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
| Site mirror, raw pages | `../agentic-design-mirror/pages/raw/patterns/**` | Next.js RSC payload (`self.__next_f.push`) with the pattern object | © KORTEXYA; personal education only. Extracted `content.*` for these 277 records is **gitignored** and rebuilt locally. |
| Free pack | `../agentic-design-mirror/patterns-pack-free/data/patterns.json` | 11 tool-use records: `id, name, category, categoryName, complexity, description, features, useCases, tldr, example, code, references` | "Free to use in your own projects … do not republish as your own." The 11 records are committed as sample data with the pack README quoted. |
| Free pack MCP server | `…/patterns-pack-free/mcp-server/server.mjs` | tool names and shapes | Reused as naming precedent only (cited); no code copied. |
| Free pack Markdown sheets | `…/patterns-pack-free/markdown/tool-use/*.md` | sheet layout | Layout reused for compiled reference sheets (cited). |

Measured 2026-09-12: all 288 records have `tldr`, flow `nodes/edges`, `references`, `codeExamples`;
35 also have `whenToUse, bestPractices, commonPitfalls, steps, implementationGuide`. Field coverage
is therefore uneven and every compiled view must tolerate absent optional fields.

## 4. Data model

### 4.1 Pattern record

One file per pattern: `catalog/patterns/<category>/<slug>.json`. Pydantic v2 models in
`src/agentic_patterns_catalog/model.py` are the source of truth; `schema/pattern.schema.json`
(JSON Schema 2020-12) is generated from them and a test asserts the committed file equals a fresh
generation.

```
id            "<category>/<slug>"              stable key; equals the pack id where one exists
name, category, kind, complexity
  kind        pattern | technique | benchmark | tool      (SP4+ sections add values; closed enum)
content       description, tldr{what, when, watchOut}, features[], useCases[], whenToUse[],
              bestPractices[], commonPitfalls[], steps[], example, code{typescript, python, rust},
              references[], flow{nodes[], edges[]}
              — field names identical to the pack's patterns.json; all optional except description, tldr
selection     problem_signals[], preconditions[], contraindications[],
              facets{scale, latency_cost, token_cost, risk_class, maturity}      closed enums, see 4.2
              relations[{type, target, prefer_when}]
                type ∈ alternative_to | composes_with | requires | precedes
provenance    source{url, mirrored_at, extraction ∈ rsc-payload | free-pack, content_sha256}
              enrichment{<selection field>: {method ∈ llm-draft | human | derived,
                                              model, date, reviewed_by | null}}
```

### 4.2 Facet vocabulary (closed; changing it is a schema change)

| Facet | Values |
|---|---|
| `scale` | single-agent, multi-agent, fleet |
| `latency_cost` | none, adds-1-llm-call, adds-n-llm-calls, async-only |
| `token_cost` | low, medium, high |
| `risk_class` | misroute, data-leak, unsafe-action, cost-runaway, quality-drift, none |
| `maturity` | research, emerging, production |

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

SP1 ships two recipes, authored by hand from the documents named in ADR-0001 §2 response:

- `co-scientist-digital-lab`: supervisor → generation → reflection → tournament ranking →
  proximity → evolution → meta-review, with async task framework and context memory. Source: the
  "Towards an AI co-scientist" (Gottweis, Weng, Daryin, Tu et al., Google, 2025-02-18; local copy
  `../agentic-design-mirror/goggle_ai_coscientist.pdf`). This repository is an independent
  implementation from the public paper; it reuses no prior code.
- `drone-flight-plan`: knowledge grounding → plan generation → validate against rules → SORA risk
  score → document → HITL sign-off. Source: `drone_flightplan_usecase (1).md` §1 and §3,
  `drone_sora_hazards_bundle.md`.

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

1. Facet pre-filter (exact match on declared facets; absent facet = no filter).
2. BM25 over `name + tldr.* + problem_signals + useCases + whenToUse` (`rank_bm25`, MIT).
3. Semantic arm over the same text with `fastembed` (Apache-2.0, local ONNX); skipped when the
   `embed` extra is absent and the result says so in `retrieval_path`.
4. Reciprocal Rank Fusion, `k_rrf = 60`; ties broken by id for determinism.
5. Top-k hits, each with `score_bm25, score_semantic, rrf_rank, retrieval_path
   (bm25 | semantic | rrf)`, the record's `provenance`, `reviewed`, and 1-hop `relations`.

Envelope fields (always present; `null` when not applicable, never absent):
`hits[], retrieval_path, catalog_version (git sha of catalog/), auth{subject}, empty_message | null`.

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
| `skills/agentic-patterns/generated/CATALOG.md` | one line per record. Pack records: `id — tldr.what — use when: tldr.when`. The other 277: `id — name — first problem_signal` when enriched, `id — name` until then, so no site prose is committed. `compile --local` may use `tldr` for all 288 for local use and the smoke test; that output is gitignored. | token estimate (`len(text) / 4`) asserted under 16k |
| `skills/agentic-patterns/generated/guides/<category>.md` | comparison table of the category's patterns by facets; `alternative_to` rows with `prefer_when` | every pattern of the category appears once |
| `skills/agentic-patterns/generated/sheets/<id>.md` | full reference sheet, pack layout | only for the 11 pack records in git; all 288 locally |
| `catalog/embeddings/<model>.npy` + ids | semantic arm index | gitignored; rebuilt by compile |

`skills/agentic-patterns/SKILL.md` (hand-written) states the four-step contract: read CATALOG.md →
open the category GUIDE or call `select` → apply the full record → check `contraindications`
before committing to a pattern.

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

- `eval/tasks.jsonl`: ~30 cases `{task, expected_ids[], expected_path, notes}`. At least five come
  from each recipe's use case (biomedical analysis, drone flight planning) so the recipes are also
  eval fixtures.
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

- `uv run catalog verify`: every record validates; `index.json` matches files; relation targets
  resolve; `precedes` acyclic; recipe `pattern_id`s resolve; committed schema equals generated;
  `CATALOG.md` under budget; compiled outputs equal a fresh compile; `eval.json` within declared
  tolerance; every configured store passes the same checks. CI runs it on the 11 committed records;
  locally it runs on all 288.
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
| SP5 | Co-Scientist blueprint (generic digital lab from the Co-Scientist paper; Celery task framework) | recipe `co-scientist-digital-lab` |
| SP6 | Drone fleet blueprint (flight plan, SORA, PX4 SITL) | recipe `drone-flight-plan` |
| SP7 | Composer (use case → agent set) | recipes + `select` |
| SP8 | BML loop + digital twin (Airflow vs Prefect vs LangGraph decided here) | `Ledger`, `eval.json` shape |
| SP9 | Edge / cloud deploy | none in SP1 |

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
9. Two recipes; recipe checks in `verify`; recipe-derived eval cases.
10. Enrichment across priority categories; CI.

Parallel tracks once step 2 lands: SP2's fuller design and SP3's rego learning can proceed against
the `Store`/`PolicyDecisionPoint` interfaces without blocking steps 3–5.
