# Tool Use — guide

External tool integration and function calling patterns

## When to use

- Tasks requiring real-time or current information not available in training data
- Applications needing precise calculations or data analysis beyond text generation
- Systems that must interact with external APIs or databases
- Workflows requiring file manipulation or system operations
- Scenarios where verification or execution of generated code is needed
- Applications requiring integration with existing business systems

## Best practices

- Design robust error handling for tool failures and network issues
- Implement proper authentication and security measures for tool access
- Use tool abstraction layers to simplify integration and maintenance
- Validate tool inputs and sanitize outputs to prevent security issues
- Implement rate limiting and resource management for tool usage
- Provide clear documentation and examples for each available tool
- Monitor tool usage and performance for optimization opportunities

## Common pitfalls

- Insufficient error handling leading to system failures when tools are unavailable
- Security vulnerabilities from improper input validation or excessive permissions
- Over-reliance on tools for tasks that could be handled with AI capabilities alone
- Poor tool selection leading to inefficient or incorrect task execution
- Not considering the latency and cost implications of external tool usage
- Inadequate monitoring and logging of tool interactions for debugging

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| agent-skills | Agent Skills | medium |  |  |  |  |  |
| code-as-action | Code as Action (CodeAct) | high |  |  |  |  |  |
| code-execution | Code Execution | high |  |  |  |  |  |
| computer-use | Computer Use | high |  |  |  |  |  |
| control-plane | Control Plane as a Tool | medium |  |  |  |  |  |
| function-calling | Function Calling | medium |  |  |  |  |  |
| mcp-tool-gateway | MCP Gateway (Tool Federation & Governance) | high |  |  |  |  |  |
| model-context-protocol | Model Context Protocol | high |  |  |  |  |  |
| structured-outputs | Structured Outputs | medium |  |  |  |  |  |
| structured-reflection-tool | Structured Reflection (Think Tool) | low |  |  |  |  |  |
| tool-retrieval | Tool Retrieval (Tool RAG) | medium |  |  |  |  |  |
