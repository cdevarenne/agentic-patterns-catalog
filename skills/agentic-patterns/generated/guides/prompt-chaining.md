# Prompt Chaining — guide

Multi-step prompt orchestration patterns

## When to use

- Tasks requiring multiple distinct processing phases with different objectives
- Complex workflows where intermediate validation or human oversight is needed
- Processes that benefit from specialized prompts optimized for specific subtasks
- Scenarios requiring dynamic branching based on intermediate results
- Applications where error recovery and retry logic are important
- Systems needing to maintain context and state across multiple interactions

## Best practices

- Design clear interfaces between chain steps with well-defined input/output contracts
- Implement proper error handling and fallback mechanisms at each step
- Use context management to maintain relevant information across the chain
- Validate intermediate results before proceeding to prevent error propagation
- Design chains to be modular and reusable across different workflows
- Monitor performance and costs across the entire chain for optimization
- Implement logging and observability for debugging and improvement

## Common pitfalls

- Creating overly complex chains that could be simplified with fewer, more capable prompts
- Poor context management leading to information loss between chain steps
- Insufficient error handling causing entire chains to fail on single step errors
- Ignoring latency and cost implications of multi-step processing
- Tight coupling between steps making the chain brittle and hard to modify
- Not validating intermediate outputs leading to cascading quality issues

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| conditional-chaining | Conditional Chaining | high |  |  |  |  |  |
| feedback-chaining | Feedback Chaining | medium |  |  |  |  |  |
| hierarchical-chaining | Hierarchical Chaining | high |  |  |  |  |  |
| iterative-refinement | Iterative Refinement | medium |  |  |  |  |  |
| parallel-chaining | Parallel Chaining | medium |  |  |  |  |  |
| parallel-synthesis | Parallel Synthesis | high |  |  |  |  |  |
| sequential-chaining | Sequential Chaining | low |  |  |  |  |  |
