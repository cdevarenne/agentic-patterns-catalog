# Exploration & Discovery — guide

Patterns for search, experimentation, adaptation, and solution discovery

## When to use

- The best action is initially uncertain and feedback arrives over time
- The candidate space is too large for exhaustive search
- Controlled experimentation is permitted and measurable

## Best practices

- Define safe exploration boundaries and rollback conditions
- Separate offline evaluation from guarded online experiments
- Track regret, coverage, and downstream impact rather than reward alone

## Common pitfalls

- Exploring directly in high-risk production decisions
- Optimizing a proxy reward that diverges from user value
- Ignoring delayed effects and changing environments

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| curiosity-driven-search | Curiosity-Driven Exploration | high |  |  |  |  |  |
| evolutionary-algorithms | Evolutionary Discovery Algorithms | high |  |  |  |  |  |
| multi-armed-bandits | Multi-Armed Bandit Optimization | medium |  |  |  |  |  |
| reinforcement-learning | Reinforcement Learning Exploration | high |  |  |  |  |  |
