# ADR-0003 — The tracked record is our enrichment; site content is a rebuildable cache

Date: 2026-09-15
Status: Accepted (decision only — not yet implemented; see issue #4).
Amends spec §3, §4.1, §4.6 and §7. Supersedes nothing.

## Context

A pattern record holds two halves in one file:

| half | author | reproducible | redistributable |
|---|---|---|---|
| `content` | agentic-design.ai | yes, by `catalog extract` from the local mirror | no, except the 11 free-pack records |
| `selection` — problem_signals, preconditions, contraindications, facets, relations | this project | no; LLM-drafted then human-reviewed | yes; it is the project's own contribution |

`.gitignore` filters by path, not by field, so the rule that correctly keeps the site's prose out of
git also keeps our enrichment out for 277 of 288 records. Today that costs nothing — no record has
any enrichment yet. After Plan E it would mean the enrichment exists on one disk, untracked: no
history, no backup, lost to `git clean -fdx` or a fresh clone, and never publishable, while spec §7
says the repository ships enrichment for all 288.

## Decision

Invert which half is primary.

- `catalog/patterns/<category>/<id>.json` is **tracked for all 288 records** and holds identity
  (`id`, `name`, `category`, `kind`, `complexity`), `selection`, and `provenance`. It carries no site
  prose, so it is ours to publish.
- Site content becomes a rebuildable cache outside the catalog tree, gitignored, written by
  `catalog extract` for the 277 and by `catalog seed` for the 11 from the already-tracked
  `data/pack/patterns.json`.
- `FileStore` merges the cache onto the tracked record at load. `Pattern.content` becomes optional:
  a checkout with no cache is valid and still supports `select` over `selection` text, the compiled
  category index, and every identity-level check. `catalog verify` reports a missing cache as a
  warning, not a failure, and the commands that need prose (`compile` sheets, `get_example`) say
  which command rebuilds it.

## Why this and not a separate enrichment file

A split (`catalog/enrichment/<id>.json` merged onto a gitignored content record) solves the same
problem, but it leaves the untracked file as the primary one. Naming the tracked file the record
matches what the repository is: our catalog, with the site's prose as an input we cache. It also
matches how the mirror is already treated — an input, rebuilt on demand, never the artifact.

## Consequences

- `content_hash` and `content_sha256` describe the cache, not the tracked record. `content_version`
  (spec §5) is derived from those hashes, so a checkout without a cache cannot compute it; the
  tracked records need their own version, or `content_version` moves to the cache and the envelope
  reports `null` when no cache is present. Settle this when implementing.
- The 11 free-pack records lose their committed `content` blocks; the same prose stays tracked in
  `data/pack/patterns.json`, which is where the licence note already lives. No licensed text is lost.
- `.gitignore` inverts: `catalog/patterns/` becomes tracked, the content cache directory ignored.
- Cheapest moment to implement is before any enrichment exists, which is now.
