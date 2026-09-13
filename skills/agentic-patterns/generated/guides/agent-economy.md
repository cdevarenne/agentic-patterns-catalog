# Agent Economy & Interop Protocols — guide

Payments, commerce, discovery, identity, and web contracts for the agentic internet

## When to use

- Agents need to spend money, transact, or access paid resources on a user behalf
- Agents and tools must find and authenticate each other without bespoke wiring
- A site or service needs to expose content or APIs to agents and control that access

## Best practices

- Bind authority to signed, scoped, expiring mandates rather than shared credentials
- Verify counterparty identity and reputation before transacting, with an escrow or fallback
- Treat several of these standards as emerging or draft and design for change

## Common pitfalls

- Handing an agent a blank check or raw card details instead of a scoped token
- Trusting an unknown agent purely on its self-description
- Assuming any single 2025-2026 protocol is final and universally adopted

## Patterns

| id | name | complexity | scale | latency_cost | token_cost | risk_class | maturity |
|---|---|---|---|---|---|---|---|
| agent-payment-mandates | Agent Payment Mandates (AP2) | high |  |  |  |  |  |
| agent-readable-web | Agent-Readable Web (llms.txt / NLWeb) | medium |  |  |  |  |  |
| agent-registry-discovery | Agent Registry & Discovery | medium |  |  |  |  |  |
| agentic-commerce-protocol | Agentic Commerce Protocol (ACP) | high |  |  |  |  |  |
| http-native-micropayments | HTTP-Native Micropayments (x402) | high |  |  |  |  |  |
| inter-agent-trust-reputation | Inter-Agent Trust & Reputation | high |  |  |  |  |  |
| web-bot-auth | Web Bot Auth (Signed Agents) | medium |  |  |  |  |  |
