# Function Calling

Category: tool-use | Complexity: medium

Structured interface for AI to invoke external functions and APIs

## In 30 seconds

- **What:** AI invokes external functions via structured schemas, passing validated parameters and receiving typed responses.
- **When:** Tasks requiring real-time data, calculations, or state changes that the model cannot perform internally.
- **Watch out:** Models may hallucinate function calls with wrong names, missing parameters, or impossible argument values.

## Key features

- Schema-based function definitions
- Parameter validation
- Return value handling
- Error management

## Use cases

- api-integration
- system-automation
- Data Processing
- external-services

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Function Definition:
{
  "name": "get_weather",
  "description": "Get current weather",
  "parameters": {
    "location": "string",
    "units": "celsius|fahrenheit"
  }
}

AI Call:
get_weather(location="New York", units="celsius")

Response: {"temp": 22, "condition": "sunny"}
```

## Implementation (python)

```python
#!/usr/bin/env python3

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: Dict[str, Dict[str, str]]
    required: List[str]

@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]

class ToolRegistry:
    def __init__(self):
        self.schemas: Dict[str, ToolSchema] = {}
        self.impls: Dict[str, Callable[[Dict[str, Any]], str]] = {}

    def register(self, schema: ToolSchema, impl: Callable[[Dict[str, Any]], str]) -> None:
        self.schemas[schema.name] = schema
        self.impls[schema.name] = impl

    # Validate the emitted call against the schema, then execute it.
    def dispatch(self, call: ToolCall) -> str:
        schema = self.schemas.get(call.name)
        if schema is None:
            return f'Error: unknown tool "{call.name}"'
        for key in schema.required:
            if key not in call.arguments:
                return f'Error: missing required argument "{key}" for {call.name}'
        for key, spec in schema.parameters.items():
            if key in call.arguments and spec["type"] == "string" and not isinstance(call.arguments[key], str):
                return f'Error: argument "{key}" must be string'
        return self.impls[call.name](call.arguments)

# Model stub: chooses a tool + arguments from the user query.
def model_decide(query: str) -> Optional[ToolCall]:
    q = query.lower()
    if "weather" in q:
        city = "unknown"
        if " in " in q:
            tail = query[q.index(" in ") + 4:]
            city = tail.replace("?", "").strip().split(" ")[0]
        return ToolCall("get_weather", {"city": city})
    if "+" in q or "compute" in q or "plus" in q:
        expression = "".join(ch for ch in query if ch in "0123456789+*")
        return ToolCall("calculator", {"expression": expression})
    return None

# Tiny safe evaluator for sums of products, e.g. "2*3+4".
def calc(expr: str) -> int:
    total = 0
    for term in expr.split("+"):
        if not term:
            continue
        product = 1
        for n in term.split("*"):
            product *= int(n)
        total += product
    return total

def main():
    registry = ToolRegistry()
    registry.register(
        ToolSchema("get_weather", "Current weather for a city",
                   {"city": {"type": "string", "description": "city name"}}, ["city"]),
        lambda args: f'Weather in {args["city"]}: 72F, partly cloudy',
    )
    registry.register(
        ToolSchema("calculator", "Evaluate an arithmetic expression",
                   {"expression": {"type": "string", "description": "expression"}}, ["expression"]),
        lambda args: f'{args["expression"]} = {calc(args["expression"])}',
    )

    queries = ["What is the weather in Paris?", "Compute 3+4+5", "Tell me a story"]
    for query in queries:
        print(f"\nUser: {query}")
        call = model_decide(query)
        if call is None:
            print("Model: (no tool needed) answering directly.")
            continue
        print(f"Model -> tool_call {call.name}({call.arguments})")
        result = registry.dispatch(call)
        print(f"Tool result: {result}")
        print(f"Model -> final answer: {result}")

if __name__ == "__main__":
    main()
```

## References

- ReAct: Synergizing Reasoning and Acting in Language Models (ICLR 2023) - https://arxiv.org/abs/2210.03629
- Toolformer: Language Models Can Teach Themselves to Use Tools (2023) - https://arxiv.org/abs/2302.04761
- Gorilla: Large Language Model Connected with Massive APIs (UC Berkeley 2023) - https://arxiv.org/abs/2305.15334
- Berkeley Function Calling Leaderboard (BFCL) - Current Benchmark - https://gorilla.cs.berkeley.edu/leaderboard.html
- Anthropic Claude Tool Use Documentation - https://docs.anthropic.com/en/docs/tool-use

---
Source: https://agentic-design.ai/patterns/tool-use/function-calling (extraction: free-pack, content sha256 c354e95ff3e1…)
