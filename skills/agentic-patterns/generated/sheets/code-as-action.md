# Code as Action (CodeAct)

Category: tool-use | Complexity: high

Instead of emitting one JSON tool call per turn, the agent's action space is executable code that orchestrates tools with loops, conditionals, and variables. A single code block can call many tools, branch on results, and keep intermediate data in the runtime rather than passing every result back through the context window. Anthropic reports roughly a 98 percent token reduction on some multi-tool workflows when tools are called from code via MCP.

## In 30 seconds

- **What:** Agent writes executable code that calls multiple tools with loops, conditionals, and variables in a single turn, keeping intermediate results in runtime.
- **When:** Multi-tool workflows with iteration, branching, or state that would otherwise require many sequential model round-trips and context window passes.
- **Watch out:** Code execution errors halt the entire workflow; agent must debug and retry, and sandboxing overhead can negate token savings on simple tasks.

## Key features

- Action space is executable code, not a single JSON call
- Loops, conditionals, and variables compose many tool calls per turn
- Intermediate results stay in the runtime, not the context window
- Fewer model round-trips for multi-step, multi-tool work
- Large token reduction on tool-heavy workflows (up to ~98 percent reported)
- Tools exposed to code (for example via MCP) with results filtered before return

## Use cases

- multi-tool-workflows
- batch-processing
- token-optimization
- data-orchestration
- agent-runtimes

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Task: "For each of the 500 rows in orders.csv, look up the customer, compute tax, and return the total that is overdue"

JSON-tool-call way: 20+ sequential calls just to iterate, each result round-tripping through the context window.

CodeAct way, the agent writes one script:
```python
rows = read_csv("orders.csv")               # tool
total = 0
for r in rows:                              # loop stays in runtime
    c = get_customer(r["id"])               # tool
    tax = compute_tax(r["amount"], c.region)  # tool
    if r["due"] < today:
        total += r["amount"] + tax
print(total)
```
Only the final total returns to the model.

Result: 500 rows processed with 3 tools in one turn; the 500 intermediate customer records never enter the context, cutting tokens by roughly 98 percent versus per-row tool calls
```

## Implementation (python)

```python
#!/usr/bin/env python3

# Code as Action (CodeAct).
# The agent's action is one structured program (loops, conditionals,
# variables) that orchestrates three tools over 500 orders in a single turn.
# A tiny interpreter walks the fixed op structure; nothing is eval'd. The 500
# intermediate records stay in the runtime, and only the final total returns.

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Union

TODAY = 15
RATES: Dict[str, float] = {"eu": 0.2, "us": 0.08, "apac": 0.1, "latam": 0.15}


# Simulated tools. Each returns canned-but-deterministic data.
def read_csv() -> List[Dict[str, int]]:
    rows: List[Dict[str, int]] = []
    for i in range(500):
        rows.append({"id": i, "customer_id": 1 + (i % 20), "amount": 50 + ((i * 37) % 950), "due_day": 1 + ((i * 7) % 28)})
    return rows


def get_customer(cid: int) -> Dict[str, Any]:
    regions = ["eu", "us", "apac", "latam"]
    return {"id": cid, "region": regions[cid % len(regions)]}


def compute_tax(amount: float, region: str) -> float:
    return round(amount * RATES[region], 2)


TOOLS: Dict[str, Callable[[List[Any]], Any]] = {
    "read_csv": lambda args: read_csv(),
    "get_customer": lambda args: get_customer(args[0]),
    "compute_tax": lambda args: compute_tax(args[0], args[1]),
}


@dataclass
class LoadOp:
    result: str
    tool: str
    arg: str


@dataclass
class CallOp:
    result: str
    tool: str
    args: List[str]


@dataclass
class GuardOp:
    ref: str
    less_than: int
    into: str
    add: List[str]


@dataclass
class ForeachOp:
    item_var: str
    list_var: str
    body: List[Union[CallOp, GuardOp]]


@dataclass
class ReturnOp:
    ref: str


@dataclass
class Stats:
    tool_calls: int = 0
    rows: int = 0
    overdue: int = 0
    records: int = 0


# Resolve a reference like "r.amount" or a plain var like "tax" from runtime.
def resolve(runtime: Dict[str, Any], ref: str) -> Any:
    if "." in ref:
        var, key = ref.split(".")
        return runtime[var][key]
    return runtime[ref]


# The interpreter: one turn executes the whole program, tools included.
def run_program(program: List[Union[LoadOp, ForeachOp, ReturnOp]]) -> Any:
    runtime: Dict[str, Any] = {"total": 0}
    stats = Stats()
    returned: float = 0
    for op in program:
        if isinstance(op, LoadOp):
            runtime[op.result] = TOOLS[op.tool]([op.arg])
            stats.tool_calls += 1
            stats.rows = len(runtime[op.result])
        elif isinstance(op, ForeachOp):
            for item in runtime[op.list_var]:
                runtime[op.item_var] = item
                for step in op.body:
                    if isinstance(step, CallOp):
                        args = [resolve(runtime, a) for a in step.args]
                        runtime[step.result] = TOOLS[step.tool](args)
                        stats.tool_calls += 1
                        if step.tool == "get_customer":
                            stats.records += 1  # stays in runtime
                    else:
                        if resolve(runtime, step.ref) < step.less_than:
                            delta = sum(resolve(runtime, a) for a in step.add)
                            runtime[step.into] = runtime[step.into] + delta
                            stats.overdue += 1
        elif isinstance(op, ReturnOp):
            returned = runtime[op.ref]
    return returned, stats


def main() -> None:
    print("Code as Action, one program orchestrates 3 tools over 500 orders\n")

    # The agent's single code action, expressed as a fixed op structure.
    program: List[Union[LoadOp, ForeachOp, ReturnOp]] = [
        LoadOp("rows", "read_csv", "orders.csv"),
        ForeachOp("r", "rows", [
            CallOp("c", "get_customer", ["r.customer_id"]),
            CallOp("tax", "compute_tax", ["r.amount", "c.region"]),
            GuardOp("r.due_day", TODAY, "total", ["r.amount", "tax"]),
        ]),
        ReturnOp("total"),
    ]

    print("Code action (interpreted, never eval'd):")
    print('  rows = read_csv("orders.csv")')
    print("  total = 0")
    print("  for r in rows:")
    print("      c = get_customer(r.customer_id)")
    print("      tax = compute_tax(r.amount, c.region)")
    print(f"      if r.due_day < {TODAY}:")
    print("          total += r.amount + tax")
    print("  return total\n")

    total, stats = run_program(program)

    print("Execution (single turn):")
    print(f"  rows processed        : {stats.rows}")
    print(f"  tool calls made       : {stats.tool_calls} (read_csv + 2 per row)")
    print(f"  customer records built: {stats.records} (kept in runtime, never returned)")
    print(f"  overdue orders        : {stats.overdue}")
    print(f"  total returned        : {total:.2f}\n")

    json_round_trips = 1 + stats.rows * 2
    print("Context traffic:")
    print("  CodeAct: 1 value returned to the model")
    print(f"  JSON-call way: {json_round_trips} tool results would round-trip through context")
    print("The intermediate records never entered the context window.")


if __name__ == "__main__":
    main()
```

## References

- Executable Code Actions Elicit Better LLM Agents (CodeAct) - https://arxiv.org/abs/2402.01030
- Anthropic - Code execution with MCP - https://www.anthropic.com/engineering/code-execution-with-mcp
- Hugging Face smolagents - code-writing agents - https://huggingface.co/docs/smolagents

---
Source: https://agentic-design.ai/patterns/tool-use/code-as-action (extraction: free-pack, content sha256 0a93b3e266c7…)
