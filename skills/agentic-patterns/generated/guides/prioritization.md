# Prioritization — guide

Transparent ranking, scheduling, and multi-criteria decision patterns

## When to use

- Several valid objectives compete for limited resources
- Work needs a repeatable, explainable ordering
- Priorities must adapt as context or evidence changes

## Best practices

- Document criteria, weights, constraints, and decision owners
- Test sensitivity to plausible weight and input changes
- Monitor fairness, starvation, and ranking drift over time

## Common pitfalls

- Treating subjective weights as objective truth
- Optimizing engagement without quality or safety constraints
- Allowing low-priority work to starve indefinitely

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| dynamic-ranking | Dynamic Content Ranking | high |  |  |  |  |  |
| multi-criteria-decision | Multi-Criteria Decision Analysis | high |  |  |  |  |  |
| priority-queues | Dynamic Priority Queue Systems | medium |  |  |  |  |  |
| weighted-scoring | Multi-Criteria Weighted Scoring | medium |  |  |  |  |  |
