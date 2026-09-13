# Reflection — guide

Self-evaluation and iterative improvement patterns

## When to use

- Applications requiring high accuracy and quality assurance
- Systems that need to provide explanations for their decisions
- Complex reasoning tasks where errors can compound
- Learning systems that need to adapt and improve over time
- High-stakes applications where self-validation is critical
- Systems requiring transparency and auditability

## Best practices

- Define clear criteria and metrics for self-evaluation
- Implement multiple reflection cycles for complex tasks
- Balance reflection depth with computational efficiency
- Use diverse evaluation perspectives to avoid blind spots
- Maintain logs of reflection processes for analysis and improvement
- Design stopping criteria to prevent infinite reflection loops
- Integrate human feedback to calibrate reflection effectiveness

## Common pitfalls

- Over-reflecting leading to analysis paralysis and high computational costs
- Using biased or insufficient criteria for self-evaluation
- Reflection becoming too narrow and missing important aspects
- Not acting on reflection insights to actually improve outputs
- Creating reflection loops that reinforce rather than correct errors
- Ignoring the computational overhead of extensive reflection processes

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| llm-as-judge | LLM as Judge | low |  |  |  |  |  |
| producer-critic | Producer-Critic Pattern | medium |  |  |  |  |  |
| reflexion-pattern | Reflexion | high |  |  |  |  |  |
| self-critique | Self-Critique | medium |  |  |  |  |  |
