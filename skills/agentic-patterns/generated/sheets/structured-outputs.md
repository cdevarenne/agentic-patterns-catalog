# Structured Outputs

Category: tool-use | Complexity: medium

Guarantee that model output conforms to a schema by constraining decoding. A JSON Schema, regex, or grammar is compiled into a finite-state machine, and at every decode step the tokens that would violate the schema are masked out so only valid continuations can be sampled. In strict mode this makes malformed JSON and invalid tool arguments impossible. It is available natively at OpenAI, Google, and Anthropic and in open libraries such as Outlines and vLLM.

## In 30 seconds

- **What:** Compiles a schema into a finite-state machine and masks invalid tokens at each decode step, guaranteeing output conforms to the schema.
- **When:** Extracting structured data, calling tools, or generating JSON where parse errors or invalid values would break downstream code.
- **Watch out:** Schema constraints can force the model to emit technically valid but semantically nonsensical values when the true answer falls outside allowed options.

## Key features

- Constrained decoding driven by JSON Schema, regex, or grammar
- Schema compiled to a finite-state machine and per-step token mask
- Invalid tokens masked at every decode step in strict mode
- Schema-conforming output guaranteed, not merely requested
- Eliminates JSON parse errors and invalid tool-call arguments
- Native provider support plus Outlines and vLLM

## Use cases

- structured-extraction
- reliable-tool-calls
- data-pipelines
- api-responses
- schema-validation

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Task: extract {name: string, amount: number, currency: enum[USD, EUR, GBP]} from 10000 receipts.

1. Compile the JSON Schema into an FSM once
2. At each decode step, mask any token that would break the schema (wrong type, unknown enum value, missing quote)
3. The model can only emit valid continuations, so it returns e.g. {"name":"Acme","amount":42.5,"currency":"USD"}
4. Downstream code runs json.loads() with no try/except and no repair step

Result: 0 schema violations across all 10000 rows; parse-failure retries drop from a routine cost to zero
```

## Implementation (python)

```python
#!/usr/bin/env python3
# Structured Outputs: constrained decoding against a JSON schema. The schema is
# compiled to a finite-state machine; at every decode step the tokens that would
# break the schema are masked out, so the model can only emit a valid continuation.
# Here we classify a support ticket into a fixed shape and watch invalid tokens fail.

import json
from typing import List

def is_digit(t: str) -> bool:
    return len(t) == 1 and "0" <= t <= "9"

# Enum field: the FSM allows only the schema's literal values.
def constrained_choice(field: str, allowed: List[str], ranks: List[str]) -> str:
    print(f"  field '{field}' (enum {'|'.join(allowed)})")
    print(f"     model ranks: {', '.join(ranks)}")
    for tok in ranks:
        if tok in allowed:
            print(f"       token '{tok}' ALLOWED -> emit")
            return tok
        print(f"       token '{tok}' BLOCKED (not in enum)")
    return allowed[0]

# Number field: digits, at most one decimal point, and a STOP that ends on a digit.
def number_allowed(tok: str, state: str) -> bool:
    if tok == "STOP":
        return len(state) > 0 and is_digit(state[-1])
    if tok == ".":
        return "." not in state
    return is_digit(tok)

def constrained_number(field: str, steps: List[List[str]]) -> str:
    print(f"  field '{field}' (number)")
    state = ""
    for i, ranks in enumerate(steps, start=1):
        print(f"     step {i} ranks: {', '.join(ranks)}")
        for tok in ranks:
            if number_allowed(tok, state):
                if tok == "STOP":
                    print("       'STOP' ALLOWED -> end number")
                    return state
                print(f"       '{tok}' ALLOWED -> emit")
                state += tok
                break
            why = "second decimal point" if tok == "." else "not a number token"
            print(f"       '{tok}' BLOCKED ({why})")
    return state

def main() -> None:
    print("Task: extract {category: bug|billing|feature, priority: low|high, hours: number}")
    print("      from a support ticket, output constrained to a JSON schema.")
    print('Ticket: "billing charged me twice, please refund; took about 3.5 hours to notice"\n')
    print("Compiling schema to an FSM... done. Decoding under per-step token masks:\n")

    category = constrained_choice("category", ["bug", "billing", "feature"], ["refund", "billing", "bug"])
    priority = constrained_choice("priority", ["low", "high"], ["urgent", "high"])
    hours = constrained_number("hours", [["3", "x"], [".", ","], ["5"], [".", "STOP"]])

    text = f'{{"category":"{category}","priority":"{priority}","hours":{hours}}}'
    print(f"\nConstrained output: {text}")
    # Guaranteed valid by construction, so parse directly with no repair pass.
    parsed = json.loads(text)
    print("Downstream parse (no repair, no try/except): OK")
    print(f"  category={parsed['category']} priority={parsed['priority']} hours={parsed['hours']}")

if __name__ == "__main__":
    main()
```

## References

- OpenAI - Structured Outputs guide - https://platform.openai.com/docs/guides/structured-outputs
- Efficient Guided Generation for Large Language Models (Outlines, FSM-based constrained decoding) - https://arxiv.org/abs/2307.09702
- JSONSchemaBench: A Rigorous Benchmark of Structured Outputs for Language Models - https://arxiv.org/abs/2501.10868

---
Source: https://agentic-design.ai/patterns/tool-use/structured-outputs (extraction: free-pack, content sha256 4031ff6337ea…)
