# Interpretability — guide

Patterns for explaining, inspecting, and validating model and agent behavior

## When to use

- Users or reviewers need evidence behind an AI-assisted outcome
- Teams are diagnosing regressions, bias, or unexpected model behavior
- A high-impact workflow requires documented uncertainty and review

## Best practices

- Match the explanation method to the audience and decision
- Validate explanations with counterfactual or perturbation checks
- Show uncertainty and source evidence alongside explanatory summaries

## Common pitfalls

- Presenting generated rationales as faithful internal reasoning
- Using one explanation method as universal proof
- Overloading end users with low-level diagnostics

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| attention-flow-analysis | Attention Flow Analysis | medium |  |  |  |  |  |
| causal-reasoning-transparency | Causal Reasoning Transparency | high |  |  |  |  |  |
| contrastive-explanations | Contrastive Explanations | medium |  |  |  |  |  |
| latent-space-visualization | Latent Space Visualization | high |  |  |  |  |  |
| uncertainty-quantification | Uncertainty Quantification | high |  |  |  |  |  |
