# Routing — guide

Dynamic request routing and delegation patterns

## When to use

- Systems with multiple specialized models or agents serving different purposes
- Applications requiring different processing strategies based on input characteristics
- High-volume systems needing intelligent load distribution
- Multi-tenant environments with varying service level requirements
- Systems with mixed workloads requiring different resource allocations
- Applications needing geographic or regulatory compliance-based routing

## Best practices

- Implement robust classification logic to accurately identify routing criteria
- Design fallback mechanisms for when primary routes are unavailable
- Monitor routing decisions and their outcomes for continuous optimization
- Use caching and preprocessing to minimize routing decision overhead
- Implement circuit breakers to prevent cascading failures across routes
- Design routing logic to be easily configurable and updateable
- Ensure routing decisions are explainable for debugging and compliance

## Common pitfalls

- Over-complicating routing logic leading to high latency and maintenance burden
- Insufficient fallback strategies causing system-wide failures
- Poor routing criteria leading to suboptimal resource utilization
- Not monitoring routing effectiveness and missing optimization opportunities
- Creating routing bottlenecks that become single points of failure
- Ignoring the cost of routing decisions relative to processing costs

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| capability-routing | Capability Routing | high |  |  |  |  |  |
| content-based-routing | Content-Based Routing | medium |  |  |  |  |  |
| dynamic-routing | Dynamic Routing | high |  |  |  |  |  |
| embedding-based-routing | Embedding-based Routing | medium |  |  |  |  |  |
| geographic-routing | Geographic Routing | medium |  |  |  |  |  |
| llm-based-routing | LLM-based Routing | medium |  |  |  |  |  |
| load-balancing | Load Balancing | medium |  |  |  |  |  |
| machine-learning-model-based-routing | Machine Learning Model-Based Routing | high |  |  |  |  |  |
| rule-based-routing | Rule-based Routing | low |  |  |  |  |  |
