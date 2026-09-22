# ADR-0005 — MCP server and policy layer

Date: 2026-09-21
Status: Implemented in Plan C. Closes issue #7.

## Context

ADR-0001 defined the system interfaces for sub-projects SP2 (persistence and activity ledger) and
SP3 (policy layer and OPA). Spec §4.6, §6, and §6.1 specified the protocol definitions: `Store`,
`Ledger`, and `PolicyDecisionPoint`.

Issue #7 scopes the initial implementation of these interfaces as Plan C:
- An MCP server exposing the six catalog tools over stdio and Streamable HTTP.
- Google OAuth authentication for network clients.
- Authorization via `AllowlistPDP` and `OpaPDP`, logging every decision before execution.
- A Postgres mirror (`PostgresStore` and `PostgresLedger`) with pgvector on PostgreSQL 18.

## Decision

1. **Server shape**: One `FastMCP` instance supporting two transports: stdio (for local agent runtimes
   such as Claude Code) and Streamable HTTP (for networked agents). HTTP mode requires Google OAuth
   credentials and refuses to start without them.
2. **Middleware-first policy**: A `PolicyMiddleware` checks authorization and writes to the ledger
   before any tool body runs. A denied tool call short-circuits immediately with a permission error.
3. **Two-row ledger**: For allowed query calls (`select` and `search_patterns`), the ledger logs two
   append-only events: an initial `decision: allow` row with empty hits before execution, and a
   `decision: result` row containing hit IDs, `catalog_version`, and `retrieval_path` after execution.
   Denied calls and other tools write one event row.
4. **Fail-closed PDPs**: Both `AllowlistPDP` and `OpaPDP` fail closed on unconfigured subjects,
   unreachable endpoints, timeouts, or malformed responses. Parity tests ensure both implementations
   enforce identical role-to-tool permissions (`TOOLS_BY_ROLE`).
5. **Postgres as a mirror**: Files on disk remain the authoritative source of truth. `catalog sync-pg`
   populates PostgreSQL tables from files and cached embeddings. `PostgresStore` and `PostgresLedger`
   mirror records, embeddings, and activity events.

## Consequences

- **Bare install unchanged**: Core CLI and local deterministic retrieval run with zero added dependencies.
- **Three optional extras**: `mcp` (`fastmcp>=4,<5`), `pg` (`psycopg[binary]`, `pgvector`), and `embed`
  (`fastembed`). OPA integration uses Python stdlib HTTP client and requires no extra.
- **Manual Google login**: Network HTTP authentication requires a Google Cloud Web application client ID
  and secret configured in the environment (`docs/auth.md`).
- **SP7 observability**: Downstream BML loops and digital twin analysis read `result` rows in the activity ledger.

## Rulings

| # | Ruling | Why | Cost if wrong |
|---|---|---|---|
| R1 | FastMCP **4** (`fastmcp>=4,<5`), not 3 | 4.0.5 is current; the surface used is identical; starting on a superseded major is debt | One version pin |
| R2 | Ledger writes **two rows** for an allowed `select`/`search_patterns`: the decision row before the body (`decision: allow`, `hits: []`) and a `decision: result` row after it with the hit ids and `{catalog_version, retrieval_path}`. Denied calls and the other tools write one row | The spec requires the decision to be written before the body runs; hit ids exist only after it. Append-only means a second row, not an update | `ActivityEvent.decision` gains the value `result`; SP7 reads two rows per query |
| R3 | `search_patterns` = BM25 arm of the shared `Selector` (`arm_scores`), filtered by category, top `k` (default 10). No gate, no semantic arm | It is a lexical search, the free pack's shape; `select` is the ranked, gated tool | A lexical-only search that never says "empty" |
| R4 | `list_categories` is derived from the records (`{id, patterns: n}`), not from `catalog/categories/` | Category records are gitignored site content and absent on a fresh clone | No category name in the answer |
| R5 | HTTP mode **requires** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`; `CATALOG_BASE_URL` defaults to `http://localhost:8000`. Missing → exit 2 | Secure by default: no anonymous HTTP | None |
| R6 | The subject is `claims["email"]` only when `claims["email_verified"]` is `True` or `"true"`; otherwise the call is denied with reason `token has no verified e-mail` | Google tokeninfo returns `email_verified` as a string | A Google account with an unverified e-mail cannot use the server |
| R7 | `PostgresStore` has five tables: the spec's `pattern`, `pattern_embedding`, `activity` plus `category(id, doc)` and `recipe(id, doc)` | The `Store` protocol has `categories()` and `recipes()` | Two small tables |
| R8 | `pattern.doc` holds the **merged** record (content included when cached). Postgres is a local mirror, never published | The server on `CATALOG_STORE=pg` must serve content | The mirror carries licensed text; `docs/auth.md` says so |
| R9 | `pattern_embedding.vec` is an untyped `vector` (no fixed dimension) keyed by `(id, model)` | The dimension follows the model (bge-small = 384); no index is needed for 288 rows | No ANN index (not needed) |
| R10 | Postgres tests run only when `CATALOG_PG_TEST_DSN` is set; each test uses its own schema and drops it | Keeps `uv run pytest` green on a bare machine and isolates tests | A skipped suite where Postgres is absent |
| R11 | `verify` gains a `pg` check that runs only when `CATALOG_PG_DSN` is set and `psycopg` imports; it compares row counts and `content_version` between files and Postgres. Skipped otherwise, and it says so | Spec: "`verify` runs its store checks against every configured store" | None |
| R12 | The OPA binary is found by `shutil.which("opa")`, else at `$OPA_BIN`; the parity test and `opa test policy/` skip when neither resolves | The owner keeps OPA at `/opt/devel/opa`, not on `PATH`; no brew install | A skipped test on machines without OPA |
