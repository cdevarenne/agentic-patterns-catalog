# Resource-Aware Optimization — guide

Cost, latency, energy, compute, and memory optimization patterns

## When to use

- Workloads vary significantly in complexity or business value
- Latency, cost, memory, or energy has a defined budget
- The system can choose among models, tools, or computation strategies

## Best practices

- Define measurable quality and resource budgets before optimizing
- Route simple requests to the least expensive path that meets requirements
- Measure end-to-end impact under representative load

## Common pitfalls

- Optimizing token count while ignoring total latency and tool cost
- Using static routing for highly variable workloads
- Trading away reliability or safety without explicit acceptance criteria

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| adaptive-compute-scaling | Adaptive Compute Scaling | high |  |  |  |  |  |
| budget-guarded-autonomy | Budget-Guarded Autonomy | medium |  |  |  |  |  |
| cost-aware-model-selection | Cost-Aware Model Selection | medium |  |  |  |  |  |
| energy-efficient-inference | Energy-Efficient Inference | high |  |  |  |  |  |
| latency-optimization | Latency Optimization | medium |  |  |  |  |  |
| memory-optimization | Memory Optimization | high |  |  |  |  |  |
| semantic-caching | Semantic Caching | medium |  |  |  |  |  |
| sleep-time-compute | Sleep-Time Compute | medium |  |  |  |  |  |
