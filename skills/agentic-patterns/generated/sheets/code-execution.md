# Code Execution

Category: tool-use | Complexity: high

Safely execute LLM-generated code in isolated environments for calculations and data processing

## In 30 seconds

- **What:** Generates code from prompts, runs it in isolated sandboxes, captures output and errors for the agent to process.
- **When:** Tasks requiring calculations, data transformation, file processing, or verification where LLM reasoning alone is insufficient.
- **Watch out:** Sandboxes leak resources or fail silently; always validate generated code logic before execution and set hard timeouts.

## Key features

- Dynamic code generation
- Safe execution environments
- Multiple language support
- Result validation
- Error handling and debugging
- Resource management

## Use cases

- Data Analysis
- mathematical-computation
- Task Automation
- prototyping

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Data Analysis Request:

User: "Analyze sales data trends from CSV file"

Code Execution Process:
1. Generate Python code:
   ```python
   import pandas as pd
   import matplotlib.pyplot as plt
   
   df = pd.read_csv("sales_data.csv")
   monthly_sales = df.groupby("month").sum()
   trend = monthly_sales["sales"].pct_change()
   ```

2. Execute in sandboxed environment
3. Return analysis results and visualizations
4. Provide insights based on computed trends

Result: Automated data analysis with insights
```

## Implementation (python)

```python
#!/usr/bin/env python3
# Code Execution: the model emits a program as a small typed expression tree,
# not a raw string. A validator runs an allow-list security scan plus a size
# check, then a sandbox interprets the tree under CPU (step) and memory (node)
# limits. Three requests show a clean run, a blocked syscall, and a runaway loop.

from dataclasses import dataclass
from typing import List, Optional, Union

@dataclass
class Mean:
    values: List[float]

@dataclass
class Variance:
    values: List[float]

@dataclass
class Scale:
    factor: float
    of: "Node"

@dataclass
class Repeat:
    times: int
    of: "Node"

@dataclass
class Syscall:
    name: str

Node = Union[Mean, Variance, Scale, Repeat, Syscall]

ALLOWED = {"mean", "variance", "scale", "repeat"}
MAX_NODES = 32     # memory proxy
STEP_BUDGET = 200  # cpu proxy

@dataclass
class Budget:
    steps: int

def kind(n: Node) -> str:
    return type(n).__name__.lower()

def count_nodes(n: Node) -> int:
    if isinstance(n, (Scale, Repeat)):
        return 1 + count_nodes(n.of)
    return 1

# Security + resource validation, run before anything executes.
def validate(n: Node) -> Optional[str]:
    bad: Optional[str] = None

    def walk(node: Node) -> None:
        nonlocal bad
        if kind(node) not in ALLOWED:
            bad = f'blocked call "{node.name}"' if isinstance(node, Syscall) else f'disallowed op "{kind(node)}"'
        if isinstance(node, (Scale, Repeat)):
            walk(node.of)

    walk(n)
    if bad:
        return bad
    nodes = count_nodes(n)
    if nodes > MAX_NODES:
        return f"program too large ({nodes} > {MAX_NODES} nodes)"
    return None

def mean(xs: List[float]) -> float:
    return sum(xs) / len(xs)

def variance(xs: List[float]) -> float:
    m = mean(xs)
    return mean([(x - m) * (x - m) for x in xs])

# Sandboxed interpreter. Each visit spends one CPU step; over budget it aborts.
def run(n: Node, budget: Budget) -> float:
    budget.steps -= 1
    if budget.steps < 0:
        raise RuntimeError("resource limit: step budget exceeded")
    if isinstance(n, Mean):
        return mean(n.values)
    if isinstance(n, Variance):
        return variance(n.values)
    if isinstance(n, Scale):
        return n.factor * run(n.of, budget)
    if isinstance(n, Repeat):
        last = 0.0
        for _ in range(n.times):
            last = run(n.of, budget)
        return last
    raise RuntimeError("unreachable: unvalidated op reached the sandbox")

def describe(n: Node) -> str:
    if isinstance(n, Mean):
        return f"mean({len(n.values)} vals)"
    if isinstance(n, Variance):
        return "variance([" + ", ".join(str(v) for v in n.values) + "])"
    if isinstance(n, Scale):
        return f"scale({n.factor}, {describe(n.of)})"
    if isinstance(n, Repeat):
        return f"repeat({n.times}, {describe(n.of)})"
    return f'syscall("{n.name}")'

def execute(label: str, program: Node) -> None:
    print(f"\nRequest: {label}")
    print(f"  generated: {describe(program)}")
    nodes = count_nodes(program)
    print(f"  validate: nodes {nodes}/{MAX_NODES}, network blocked, allow-list {sorted(ALLOWED)}")
    problem = validate(program)
    if problem:
        print(f"  rejected before execution: {problem}")
        print("  audit: attempt logged, sandbox never entered")
        return
    budget = Budget(STEP_BUDGET)
    try:
        out = run(program, budget)
        print(f"  execute: ok, steps used {STEP_BUDGET - budget.steps}/{STEP_BUDGET}")
        print(f"  output: {out:.6f}")
    except RuntimeError as err:
        print(f"  execute: aborted after {STEP_BUDGET - budget.steps}/{STEP_BUDGET} steps")
        print(f"  reason: {err}")
    print("  cleanup: temp workspace removed, attempt logged")

def main() -> None:
    print("=== Code Execution Sandbox ===")
    print(f"limits: cpu {STEP_BUDGET} steps, memory {MAX_NODES} nodes, network blocked")
    returns = [0.12, 0.08, 0.15]

    execute("average daily return across 3 stocks", Mean(returns))
    execute("portfolio variance for 3 stocks", Scale(100, Variance(returns)))
    execute("read deployment secrets from the host", Scale(2, Syscall("read_env_secrets")))
    execute("recompute variance in a 5000-iteration loop", Repeat(5000, Variance(returns)))

    print("\nsummary: 2 executed, 1 blocked by the security scan, 1 stopped by the resource limit")

if __name__ == "__main__":
    main()
```

## References

- SandboxEval: Comprehensive Test Suite for LLM Assessment Environments - https://arxiv.org/html/2504.00018
- Security of AI Agents: System Security Perspective on Vulnerabilities - https://arxiv.org/abs/2406.08689
- Vulnerability Handling of AI-Generated Code - https://arxiv.org/abs/2408.08549
- Optimizing AI-Assisted Code Generation: Security & Quality - https://arxiv.org/html/2412.10953v1
- SWE-bench: Real-World Software Engineering Benchmark - https://www.swebench.com/

---
Source: https://agentic-design.ai/patterns/tool-use/code-execution (extraction: free-pack, content sha256 0580df3c44bf…)
