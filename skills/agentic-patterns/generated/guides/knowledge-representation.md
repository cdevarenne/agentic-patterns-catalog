# Knowledge Representation — guide

Structured knowledge, semantics, validation, and reasoning patterns

## When to use

- The domain has durable entities, relationships, taxonomies, or rules
- Consistency and provenance matter across multiple data sources
- Agents need deterministic validation or symbolic inference alongside language models

## Best practices

- Start from concrete competency questions rather than an abstract universal ontology
- Attach provenance and ownership to facts and schema changes
- Validate incoming data continuously against versioned constraints

## Common pitfalls

- Modeling every possible concept before proving a use case
- Conflating similar labels without preserving source meaning
- Allowing schema and data quality to drift without validation

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| knowledge-graph-construction | Knowledge Graph Construction | high |  |  |  |  |  |
| owl-reasoning | OWL Ontological Reasoning | high |  |  |  |  |  |
| rdf-knowledge-modeling | RDF Knowledge Modeling | medium |  |  |  |  |  |
| semantic-validation | Semantic Data Validation | high |  |  |  |  |  |
| shacl-validation | SHACL Constraint Validation | high |  |  |  |  |  |
