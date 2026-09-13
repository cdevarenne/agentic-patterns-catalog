# Workflow Orchestration — guide

Stateful, event-driven, and enterprise workflow coordination patterns

## When to use

- A task spans multiple tools, services, agents, or human approvals
- Work must survive restarts or be resumed from checkpoints
- Operators need an audit trail of state transitions and decisions

## Best practices

- Model each step with explicit inputs, outputs, ownership, and retry policy
- Use idempotency keys and durable checkpoints around side effects
- Expose workflow state, errors, and intervention controls to operators

## Common pitfalls

- Hiding business state inside conversation history
- Retrying non-idempotent actions without safeguards
- Building a central orchestrator that becomes a throughput and availability bottleneck

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| actor-model-coordination | Actor Model Coordination | high |  |  |  |  |  |
| conversational-orchestration | Conversational Orchestration | high |  |  |  |  |  |
| durable-execution | Durable Execution & Checkpointing | high |  |  |  |  |  |
| edge-ai-optimization | Edge AI Optimization | high |  |  |  |  |  |
| enterprise-orchestration | Enterprise Orchestration | high |  |  |  |  |  |
| event-driven-blackboard | Event-Driven Blackboard | medium |  |  |  |  |  |
| event-driven-hierarchical | Event-Driven Hierarchical Agents | high |  |  |  |  |  |
| event-driven-market-based | Event-Driven Market-Based | high |  |  |  |  |  |
| event-driven-orchestrator-worker | Event-Driven Orchestrator-Worker | medium |  |  |  |  |  |
| federated-orchestration | Federated Orchestration | high |  |  |  |  |  |
| graph-state-machines | Graph State Machines | medium |  |  |  |  |  |
| progressive-enhancement | Progressive Enhancement | medium |  |  |  |  |  |
| resource-aware-scheduling | Resource-Aware Scheduling | high |  |  |  |  |  |
| reversible-action-compensation | Reversible Actions & Compensation (Agent Saga) | high |  |  |  |  |  |
| role-based-teamwork | Role-Based Teamwork | medium |  |  |  |  |  |
| stateful-graph-workflows | Stateful Graph Workflows | high |  |  |  |  |  |
