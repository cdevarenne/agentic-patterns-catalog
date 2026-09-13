# Reasoning Techniques — guide

Advanced reasoning and thinking techniques

## When to use

- Complex, multi-faceted problems requiring systematic decomposition and analysis
- Applications where decision transparency and auditability are legally or ethically required
- Tasks benefiting from iterative refinement and self-correction capabilities
- Integration scenarios involving multiple information sources or external tools
- Educational contexts where demonstrating reasoning processes enhances learning outcomes
- High-stakes decisions where confidence estimation and uncertainty quantification are critical

## Best practices

- Define clear problem boundaries and success criteria before starting the reasoning process
- Implement validation checkpoints at each major reasoning step to catch errors early
- Use confidence scoring to dynamically allocate computational resources based on problem complexity
- Maintain detailed documentation of reasoning chains for debugging and improvement
- Test patterns across diverse problem domains to ensure generalizability and robustness
- Design graceful degradation strategies for when reasoning chains become computationally expensive
- Balance transparency with efficiency - not every step needs explicit documentation

## Common pitfalls

- Over-engineering simple problems that could be solved with direct approaches
- Skipping intermediate validation steps, allowing errors to propagate through the reasoning chain
- Failing to set appropriate stopping criteria for iterative processes, leading to infinite loops
- Ignoring computational cost versus accuracy trade-offs in resource-constrained environments
- Not adapting reasoning depth to match the specific problem context and requirements
- Mixing incompatible reasoning paradigms without clear transition mechanisms

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| abductive-reasoning | Abductive Reasoning | high |  |  |  |  |  |
| analogical-reasoning | Analogical Reasoning | medium |  |  |  |  |  |
| buffer-of-thoughts | Buffer of Thoughts | high |  |  |  |  |  |
| causal-reasoning | Causal Reasoning | high |  |  |  |  |  |
| chain-of-verification | Chain of Verification (CoVe) | medium |  |  |  |  |  |
| cot | Chain-of-Thought | low |  |  |  |  |  |
| fot | Forest-of-Thoughts | high |  |  |  |  |  |
| got | Graph-of-Thought | high |  |  |  |  |  |
| least-to-most | Least-to-Most Prompting | medium |  |  |  |  |  |
| lrt | Latent Recurrent Thinking | high |  |  |  |  |  |
| metacognitive-monitoring | Metacognitive Monitoring | high |  |  |  |  |  |
| proactive-clarification | Proactive Clarification & Active Disambiguation | medium |  |  |  |  |  |
| react | ReAct | high |  |  |  |  |  |
| reflective-mcts | Reflective Monte Carlo Tree Search | high |  |  |  |  |  |
| self-consistency | Self-Consistency | medium |  |  |  |  |  |
| skeleton-of-thoughts | Skeleton of Thoughts | medium |  |  |  |  |  |
| step-back-prompting | Step-Back Prompting | medium |  |  |  |  |  |
| test-time-compute | Test-Time Compute Scaling | high |  |  |  |  |  |
| tot | Tree-of-Thought | high |  |  |  |  |  |
