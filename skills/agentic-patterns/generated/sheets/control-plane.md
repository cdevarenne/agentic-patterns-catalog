# Control Plane as a Tool

Category: tool-use | Complexity: medium

Exposes a single unified tool interface to the agent while an internal control plane routes each request to the right tool, service, or model behind it. The agent prompt stays stable as the tool catalog evolves, and authentication, policy, rate limiting, and observability are enforced in one place.

## In 30 seconds

- **What:** Routes all agent tool calls through a single interface to a backend control plane that handles auth, rate limits, and tool selection without changing the agent prompt.
- **When:** You have many tools evolving frequently and need consistent policy enforcement, audit trails, and stable agent prompts across tool catalog changes.
- **Watch out:** Control plane becomes a bottleneck and single point of failure if routing logic is slow or the plane goes down, breaking all agent tool access.

## Key features

- Single stable tool interface for the agent
- Internal tool registry with dynamic routing logic
- Centralized policy, auth, and rate-limit enforcement
- Tool versioning and swaps without prompt changes
- Unified logging and observability for all tool calls

## Use cases

- enterprise-tool-integration
- large-tool-catalogs
- governance
- multi-team-platforms

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Agent request: "Analyze customer sentiment and generate a report"

Control Plane Flow:
1. Agent calls the single execute(task) tool
2. Control plane classifies the request
3. Routes to sentiment-analysis service, then report-generator
4. Applies auth, quota, and audit policies per tool
5. Aggregates results into one response

Benefit: 50+ internal tools exposed through one interface the model never has to re-learn
```

## Implementation (python)

```python
#!/usr/bin/env python3
# Control Plane as a Tool: the agent only ever calls one stable tool, execute(task).
# An internal control plane classifies the request, routes it to the right backend
# services, enforces auth scope and a quota, aggregates results, and logs every call.
# Backends can be swapped behind the interface without changing what the agent calls.

from dataclasses import dataclass
from typing import Callable, Dict, List

@dataclass
class Backend:
    name: str
    scope: str
    cost: int
    run: Callable[[str, Dict[str, str]], str]

@dataclass
class Caller:
    id: str
    scopes: List[str]
    quota: int

ORDER = ["metrics.fetch", "text.summarize", "lang.translate", "chart.render"]

def order(name: str) -> int:
    return ORDER.index(name) if name in ORDER else 99

class ControlPlane:
    def __init__(self) -> None:
        self.registry: List[Backend] = []
        self.log: List[str] = []
        self.counter = 0

    def register(self, backend: Backend) -> None:
        # Swapping a backend of the same name replaces it; the agent interface is unchanged.
        self.registry = [b for b in self.registry if b.name != backend.name] + [backend]
        self.registry.sort(key=lambda b: order(b.name))

    def classify(self, task: str) -> List[str]:
        q = task.lower()
        plan: List[str] = []
        if "revenue" in q or "metric" in q or "fetch" in q:
            plan.append("metrics.fetch")
        if "summar" in q:
            plan.append("text.summarize")
        if "translat" in q or "french" in q:
            plan.append("lang.translate")
        if "chart" in q or "render" in q or "plot" in q:
            plan.append("chart.render")
        return plan

    # The single tool the agent calls. Everything else is internal.
    def execute(self, caller: Caller, task: str) -> str:
        self.counter += 1
        plan = self.classify(task)
        print(f'Agent -> execute("{task}")')
        print(f"  [classify] route -> {', '.join(plan) or '(none)'}")
        outputs: Dict[str, str] = {}
        for name in plan:
            backend = next(b for b in self.registry if b.name == name)
            if backend.scope not in caller.scopes:
                print(f"  [policy] {name}: scope {backend.scope} MISSING -> DENY")
                self.log.append(f"req#{self.counter} {name:<16} deny-scope")
                continue
            if backend.cost > caller.quota:
                print(f"  [policy] {name}: cost {backend.cost} > quota {caller.quota} -> DENY (rate limit)")
                self.log.append(f"req#{self.counter} {name:<16} deny-quota")
                continue
            before = caller.quota
            caller.quota -= backend.cost
            print(f"  [policy] {name}: scope {backend.scope} OK, quota {before}->{caller.quota} -> ALLOW")
            outputs[name] = backend.run(task, outputs)
            print(f"  [route]  {name} -> {outputs[name]}")
            self.log.append(f"req#{self.counter} {name:<16} allow")
        if not outputs:
            response = "request denied by policy, nothing executed"
        else:
            response = " | ".join(outputs[k] for k in outputs)
        print(f"Agent <- {response}\n")
        return response

    def dump_log(self) -> None:
        print("Audit log (one line per routed backend call):")
        for entry in self.log:
            print(f"  {entry}")

def main() -> None:
    plane = ControlPlane()
    plane.register(Backend("metrics.fetch", "metrics.read", 2,
                           lambda t, ctx: "Q3 revenue 1.42M, above Q2 at 1.30M"))
    plane.register(Backend("text.summarize", "text.write", 1,
                           lambda t, ctx: f"Summary: {'revenue rose from Q2 to Q3' if ctx.get('metrics.fetch') else 'no data'}"))
    plane.register(Backend("lang.translate", "lang.write", 1,
                           lambda t, ctx: "Traduction (fr): le chiffre d affaires a progresse du T2 au T3"))
    plane.register(Backend("chart.render", "chart.render", 3,
                           lambda t, ctx: "rendered revenue-bars.png"))

    analyst = Caller("analyst-bot", ["metrics.read", "text.write", "lang.write"], 6)
    print(f"Caller {analyst.id}, scopes [{', '.join(analyst.scopes)}], quota {analyst.quota}\n")

    plane.execute(analyst, "Fetch the Q3 revenue and summarize it")
    plane.execute(analyst, "Render a chart of it")

    print("(control plane swaps text.summarize for a v2 impl; agent interface unchanged)\n")
    plane.register(Backend("text.summarize", "text.write", 1,
                           lambda t, ctx: f"Summary v2: {'Q3 beat Q2 on revenue' if ctx.get('metrics.fetch') else 'no data'}"))

    plane.execute(analyst, "Summarize the revenue again")
    plane.execute(analyst, "Fetch this quarter metrics")

    plane.dump_log()

if __name__ == "__main__":
    main()
```

## References

- Code execution with MCP: Building more efficient agents - Anthropic Engineering (2025) - https://www.anthropic.com/engineering/code-execution-with-mcp
- Envoy xDS API: the universal data plane / control plane protocol - https://www.envoyproxy.io/docs/envoy/latest/api-docs/xds_protocol

---
Source: https://agentic-design.ai/patterns/tool-use/control-plane (extraction: free-pack, content sha256 709b4816a3c7…)
