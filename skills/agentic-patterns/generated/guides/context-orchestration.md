# Context Orchestration — guide

Patterns for selecting, routing, sizing, and combining context

## When to use

- Several context sources compete for a limited model window
- Different agents or tasks need different evidence
- Context quality, privacy, or freshness varies by source

## Best practices

- Rank context by task relevance, authority, freshness, and sensitivity
- Keep provenance and access policy attached through transformations
- Evaluate retrieval and answer quality together

## Common pitfalls

- Concatenating every available source without prioritization
- Dropping provenance during summarization or handoff
- Sharing sensitive context with agents that do not need it

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| adaptive-context-depth | Adaptive Context Depth | high |  |  |  |  |  |
| context-routing | Intelligent Context Routing | medium |  |  |  |  |  |
| dynamic-context-assembly | Dynamic Context Assembly | high |  |  |  |  |  |
| multi-source-context-fusion | Multi-Source Context Fusion | high |  |  |  |  |  |
