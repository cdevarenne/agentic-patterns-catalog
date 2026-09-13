# Knowledge Retrieval (RAG) — guide

Information retrieval and augmented generation patterns

## When to use

- Applications requiring access to current, dynamic, or frequently changing information
- Domain-specific applications with specialized knowledge bases
- Systems where factual accuracy and source attribution are critical
- Applications dealing with large document collections or databases
- Scenarios where training data alone is insufficient for comprehensive responses
- Applications requiring transparency about information sources and evidence

## Best practices

- Design effective indexing and search strategies for fast and relevant retrieval
- Implement proper chunking and preprocessing of knowledge sources
- Use hybrid search approaches combining semantic similarity and keyword matching
- Design retrieval systems with appropriate filtering and ranking mechanisms
- Implement source attribution and citation capabilities for transparency
- Use retrieval quality metrics to optimize search and ranking performance
- Design systems that can handle both structured and unstructured knowledge sources

## Common pitfalls

- Poor retrieval quality leading to irrelevant or low-quality information being used in responses
- Insufficient processing of retrieved information causing context misunderstanding
- Over-reliance on retrieval without proper integration with generative capabilities
- Not implementing proper source verification and quality control for retrieved information
- Ignoring retrieval latency impact on overall system performance
- Inadequate handling of cases where relevant information cannot be retrieved

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| advanced-rag | Advanced RAG | medium |  |  |  |  |  |
| agentic-rag-systems | Agentic RAG | high |  |  |  |  |  |
| codebase-structure-retrieval | Structure-Aware Codebase Retrieval (Repo Map) | high |  |  |  |  |  |
| corrective-rag | Corrective RAG (CRAG) | high |  |  |  |  |  |
| deep-research-agent | Deep Research Agent | high |  |  |  |  |  |
| graph-rag | Graph RAG | high |  |  |  |  |  |
| hierarchical-index-retrieval | Hierarchical Index Retrieval (RAPTOR) | high |  |  |  |  |  |
| latent-knowledge-retrieval | Latent Knowledge Retrieval | high |  |  |  |  |  |
| modular-rag | Modular RAG | high |  |  |  |  |  |
| multimodal-rag | Multimodal RAG | high |  |  |  |  |  |
| naive-rag | Naive RAG | low |  |  |  |  |  |
| query-transformation-retrieval | Query Transformation Retrieval | medium |  |  |  |  |  |
| self-rag | Self-RAG | high |  |  |  |  |  |
