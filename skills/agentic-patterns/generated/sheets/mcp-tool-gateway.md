# MCP Gateway (Tool Federation & Governance)

Category: tool-use | Complexity: high

A single governed MCP entrypoint that sits in front of many backend MCP servers as a reverse proxy, federating their tools into one curated, managed tool surface that the agent connects to. Every tool call routes through the gateway, which enforces centralized authentication, per-tool authorization that separates the caller's identity from the downstream server's permissions, policy checks, rate limiting, audit logging, and telemetry. This turns a sprawling pile of independently deployed servers into one controlled integration contract, so tools can be curated, versioned, and revoked without touching each agent. Distinct from `control-plane`: the control plane is the general pattern of exposing one interface while routing internally to any tool, service, or model, whereas the MCP gateway is the MCP-ecosystem-specific realization focused on federating many MCP servers and governing the shared tool-access surface.

## In 30 seconds

- **What:** Single reverse proxy sits in front of many MCP servers, federating their tools into one curated surface with centralized auth, per-tool authorization, rate limiting, and audit logging.
- **When:** Multiple independent MCP servers need unified access control, tool curation, and audit trails without modifying each agent or backend.
- **Watch out:** Gateway becomes a critical bottleneck and single point of failure; any outage blocks all tool access across all agents and servers.

## Key features

- Reverse proxy in front of many backend MCP servers
- Federates their tools into one curated, managed tool surface
- Centralized authentication at a single entrypoint
- Per-tool authorization separating caller identity from downstream permissions
- Policy enforcement, rate limiting, and request shaping per call
- Full audit log and telemetry for every tool invocation

## Use cases

- mcp-ecosystems
- enterprise-tool-governance
- tool-federation
- audit-and-compliance
- rate-limiting

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Setup: 4 backend MCP servers (github, jira, s3-files, payments) each expose their own tools; the agent connects only to the gateway, which advertises one curated toolset.

Request: the agent calls create_issue (a Jira tool) through the gateway.

Gateway flow:
1. Authenticate the caller: validate the agent's gateway token -> identity = agent:support-bot
2. Resolve routing: create_issue maps to the jira backend server
3. Per-tool authz: support-bot is granted jira:create_issue, and the gateway swaps in its own scoped Jira service credential, so the agent never sees the downstream secret
4. Policy + rate limit: under the 60 calls/min quota -> allowed
5. Proxy the call to the jira MCP server and stream the result back
6. Audit log: {caller, tool, backend, decision=allow, latency} written

Blocked case: the agent then calls delete_repo (github). support-bot lacks github:delete_repo, so the gateway denies it before it ever reaches the backend and records decision=deny.

Result: 4 servers federated behind one entrypoint; every call is authenticated, authorized per tool, rate-limited, and audited in one place.
```

## Implementation (python)

```python
#!/usr/bin/env python3
# MCP Gateway (Tool Federation and Governance): one governed entrypoint sits in
# front of several backend MCP servers. Every call is authenticated, resolved by
# namespace to a backend, checked against a per-caller allowlist, rate-limited,
# proxied with a scoped downstream credential the agent never sees, and audited.

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

@dataclass
class BackendServer:
    name: str
    tools: List[str]
    credential: str  # held by the gateway, never exposed to the caller
    handle: Callable[[str, Dict[str, str], str], str]

@dataclass
class Request:
    token: str
    tool: str  # namespaced: "server.tool"
    args: Dict[str, str]

class Gateway:
    def __init__(self) -> None:
        self.servers: Dict[str, BackendServer] = {}
        self.tokens: Dict[str, str] = {}
        self.allow: Dict[str, List[str]] = {}
        self.audit: List[str] = []
        self.used = 0
        self.quota = 60  # calls per minute

    def federate(self, server: BackendServer) -> None:
        self.servers[server.name] = server

    def grant(self, token: str, identity: str, tools: List[str]) -> None:
        self.tokens[token] = identity
        self.allow[identity] = tools

    def _record(self, caller: str, tool: str, backend: str, decision: str) -> None:
        self.audit.append(f"caller={caller:<13} tool={tool:<22} backend={backend:<9} decision={decision}")

    def _reply(self, text: str) -> str:
        print(f"Agent <- {text}\n")
        return text

    def call(self, req: Request) -> str:
        print(f'Agent -> gateway.call(token={req.token}, tool="{req.tool}")')
        identity: Optional[str] = self.tokens.get(req.token)
        if identity is None:
            print(f"  [authn] token {req.token} -> unknown -> DENY")
            self._record("unknown", req.tool, "-", "deny-authn")
            return self._reply("authentication failed")
        print(f"  [authn] token {req.token} -> identity {identity}")

        server_name, _, bare_tool = req.tool.partition(".")
        server = self.servers.get(server_name)
        if server is None:
            print(f"  [route] namespace '{server_name}' -> no such backend -> DENY")
            self._record(identity, req.tool, "-", "deny-route")
            return self._reply("unknown tool namespace")
        print(f"  [route] namespace '{server_name}' -> {server_name} MCP server")

        if req.tool not in self.allow.get(identity, []):
            print(f"  [authz] {identity} NOT allowed {req.tool} -> DENY (before backend)")
            self._record(identity, req.tool, server_name, "deny-authz")
            return self._reply(f"{req.tool} not in caller scope")
        print(f"  [authz] {identity} allowed {req.tool} -> ALLOW")

        self.used += 1
        if self.used > self.quota:
            print(f"  [policy] over {self.quota}/min quota -> DENY (rate limit)")
            self._record(identity, req.tool, server_name, "deny-quota")
            return self._reply("rate limit exceeded")
        print(f"  [policy] under {self.quota}/min quota (used {self.used}) -> OK")

        print(f"  [creds] swap in scoped credential {server.credential} (agent never sees it)")
        result = server.handle(bare_tool, req.args, server.credential)
        print(f"  [proxy] {req.tool} -> {result}")
        self._record(identity, req.tool, server_name, "allow")
        return self._reply(result)

    def dump_audit(self) -> None:
        print("Audit log (every call, one line):")
        for line in self.audit:
            print("  " + line)

def guarded_handler(expected: str, table: Dict[str, str]) -> Callable[[str, Dict[str, str], str], str]:
    def handler(tool: str, args: Dict[str, str], cred: str) -> str:
        if cred != expected:
            return "error: bad downstream credential"
        return table.get(tool, f"error: {tool} not implemented")
    return handler

def main() -> None:
    gw = Gateway()
    gw.federate(BackendServer("calendar", ["create_event"], "cred:calendar-svc",
                              guarded_handler("cred:calendar-svc", {"create_event": "event evt-5521 created for 2 attendees"})))
    gw.federate(BackendServer("crm", ["lookup_contact"], "cred:crm-svc",
                              guarded_handler("cred:crm-svc", {"lookup_contact": "contact CRM-77: Dana Ellis"})))
    gw.federate(BackendServer("docs", ["read_file"], "cred:docs-svc",
                              guarded_handler("cred:docs-svc", {"read_file": "read 3 KB from onboarding.md"})))
    gw.federate(BackendServer("billing", ["issue_refund"], "cred:billing-svc",
                              guarded_handler("cred:billing-svc", {"issue_refund": "refund issued 40.00"})))

    gw.grant("tok-abc", "assistant-bot", ["calendar.create_event", "crm.lookup_contact", "docs.read_file"])
    print("4 MCP servers federated behind one entrypoint: calendar, crm, docs, billing\n")

    requests = [
        Request("tok-abc", "calendar.create_event", {"title": "kickoff"}),
        Request("tok-abc", "billing.issue_refund", {"order": "4821"}),
        Request("tok-bad", "calendar.create_event", {"title": "sneaky"}),
        Request("tok-abc", "crm.lookup_contact", {"id": "77"}),
    ]
    for req in requests:
        gw.call(req)
    gw.dump_audit()

if __name__ == "__main__":
    main()
```

## References

- Arcade - The MCP Gateway pattern - https://www.arcade.dev/blog/mcp-gateway-pattern/
- AWS Open Source Blog - Governing AI assets at scale with MCP Gateway and Registry - https://aws.amazon.com/blogs/opensource/governing-ai-assets-at-scale-with-mcp-gateway-and-registry/
- agentic-community - MCP Gateway and Registry reference implementation - https://github.com/agentic-community/mcp-gateway-registry

---
Source: https://agentic-design.ai/patterns/tool-use/mcp-tool-gateway (extraction: free-pack, content sha256 eaa5f0ca3272…)
