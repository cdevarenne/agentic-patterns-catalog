# ADR-0002 — Withdraw the Co-Scientist digital-lab use case

Date: 2026-09-15
Status: Accepted. Supersedes the parts of ADR-0001 that name a Co-Scientist blueprint (§2 response,
§9.1, §9.3 row SP5, §9.4 option B). ADR-0001 stays as written: it records what was decided on
2026-09-12 and why.

## Context

ADR-0001 chose two reference use cases for the catalog: a Co-Scientist-shaped digital research lab
(generate → debate → rank → evolve → meta-review) and drone fleet flight planning. The first was
modelled on "Towards an AI co-scientist" (Gottweis, Weng, Daryin, Tu et al., Google, 2025-02-18,
arXiv:2502.18864), which reports a multi-agent system producing validated biomedical hypotheses.

## Decision

Withdraw the Co-Scientist use case, its recipe (`co-scientist-digital-lab`) and its sub-project
(SP5 in ADR-0001 §9.3). Keep the drone flight-planning use case. Renumber the later sub-projects.

## Why

Kirgis, Kapoor, Schwartz et al., "Can AI agents conduct open-ended AI research? Early evidence from
two case studies" (arXiv:2607.27191v2, 2026-08-07) measures the capability the use case depends on.
The authors ran *shadow evaluations*: a well-resourced frontier agent receives the central research
question of a high-quality unpublished paper, six days of wall-clock time, thousands of dollars of
compute, GPU credits and open web access; the paper's own authors then grade the agent's output as
conference reviewers. Two NeurIPS 2026 submissions were shadowed. Both agent papers were
unambiguously rejected (overall 2/6 and 1/6, reviewers confident or certain). The agents completed
the engineering without human help but did not answer the research questions.

Five failure modes recurred, and a robustness run with a second model and scaffold reproduced them:

1. no judgment about when a problem is adequately solved — underpowered negative results presented
   as substantive findings;
2. no awareness of available resources or the timeline — both runs ended under 50% of budget;
3. no creative response to feedback about poor research design — caveats added instead of a change
   of direction;
4. ineffective backtracking — the most ambitious targets were retired in the first ten hours;
5. instruction drift — explicit rules on exploration time and paper length were ignored.

A reference instance for this catalog must demonstrate patterns on a task the patterns can actually
carry. The drone flight plan is the opposite shape: bounded, grounded in written rules, verifiable
against them, with a human sign-off gate — the "narrow, verifiable" class the same paper reports
agents do handle. It stays.

## Consequences

- `catalog/recipes/` holds one recipe in SP1; spec §4.5, §9, §12 and §14 step 9 updated.
- The patterns the withdrawn recipe exercised (supervisor orchestration, reflection, meta-review,
  asynchronous task queues, context memory) stay in the catalog, and the seven golden-set cases that
  test them stay in `eval/tasks.jsonl` with their notes re-scoped. No eval numbers change.
- `docs/architecture.mmd` drops the SP5 node and renumbers SP6–SP9 to SP5–SP8.
- Revisit if comparable evidence changes. The measurement to watch is a shadow evaluation, not a
  benchmark score: the paper's own point is that narrow verifiable benchmarks do not predict this.
