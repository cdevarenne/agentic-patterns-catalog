# Structured Reflection (Think Tool)

Category: tool-use | Complexity: low

A dedicated no-op "think" tool (Anthropic) declared in the agent tool schema that the model calls mid-trajectory to append structured reasoning between a tool result and the next action. The call has no external effect and returns nothing useful: it simply gives the model a checkpoint to re-read policy, verify constraints, and plan before acting inside a long tool-call chain. Anthropic reports a 54% relative improvement on the tau-bench airline pass^1 metric (0.570 versus a 0.370 baseline) when the tool is paired with a prompt that shows how to use it. Distinct from `metacognitive-monitoring`: that entry is the general capability of monitoring one's own reasoning, whereas the think tool is a concrete tool-schema mechanism for it, separate from extended or inference-time thinking that happens before the first response.

## In 30 seconds

- **What:** Declares a no-op tool in the schema that the model calls mid-trajectory to pause, re-read policy, and plan before the next action.
- **When:** Long tool-call chains where the model must verify constraints or policy compliance before committing to an irreversible action.
- **Watch out:** The model may skip calling think if the prompt example is weak or absent; effectiveness depends entirely on showing the model when and how to use it.

## Key features

- No-op tool in the schema: no side effect and no new data returned
- Called mid-trajectory, between a tool result and the next action
- Creates explicit reflection checkpoints inside long tool-call chains
- Used to re-check policy compliance and validate plans before acting
- Cheap and low-code: one tool definition plus a usage-guiding prompt
- Reported 54% relative pass^1 gain on the tau-bench airline domain

## Use cases

- policy-compliance
- long-tool-chains
- sequential-decision-making
- agent-reliability
- constraint-checking

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Task: an airline support agent must change a booking under fare rules.

1. The user says "Move me to tomorrow morning." The agent calls get_reservation and finds a basic-economy ticket booked 20 minutes ago
2. Before acting, the agent calls the think tool and writes out the relevant policy: basic economy is non-changeable, but a 24-hour free-cancellation window applies, and the booking is only 20 minutes old, so cancel-and-rebook is allowed; it then lists the required steps and confirmations
3. The think call returns nothing and changes no state, but the reasoning is now in context
4. Guided by that checkpoint, the agent cancels within the 24-hour window, quotes the new fare, gets user confirmation, and books, instead of illegally changing a non-changeable ticket

Result: the policy violation is avoided; on tau-bench airline this pattern lifts pass^1 from 0.370 to 0.570, a 54% relative gain
```

## Implementation (python)

```python
#!/usr/bin/env python3
# Structured Reflection (Think Tool): a dedicated no-op "think" tool sits in the
# agent's schema. Calling it takes no external action and returns no data; it
# only parks structured reasoning in context. This demo runs the same airline
# booking task twice, without and with the checkpoint, to show how the parked
# reasoning steers the agent away from a policy violation.

from dataclasses import dataclass, field
from typing import List

FREE_CANCEL_WINDOW_MIN = 24 * 60

@dataclass
class Reservation:
    fare: str
    booked_minutes_ago: int

@dataclass
class Context:
    log: List[str] = field(default_factory=list)
    plan: List[str] = field(default_factory=list)

reservation = Reservation("basic-economy", 20)

# Tools with canned effects. change_flight is illegal on a non-changeable fare.
def get_reservation(r: Reservation) -> str:
    return f"{r.fare}, booked {r.booked_minutes_ago} min ago"

def change_flight(r: Reservation) -> str:
    if r.fare == "basic-economy":
        return "POLICY VIOLATION: basic-economy fare is non-changeable"
    return "flight changed"

def cancel_booking(r: Reservation) -> str:
    free = r.booked_minutes_ago <= FREE_CANCEL_WINDOW_MIN
    return "cancelled free (within 24h window)" if free else "cancelled with penalty"

def book_flight() -> str:
    return "booked tomorrow 08:10, new fare quoted and confirmed"

# The no-op think tool: it records reasoning and a plan into context, then
# returns nothing. No booking system is touched by this call.
def think(ctx: Context, notes: List[str], plan: List[str]) -> str:
    ctx.log.extend(notes)
    ctx.plan = plan
    return ""

# Build the reflection a competent agent would write at the checkpoint.
def reflect(ctx: Context, r: Reservation) -> None:
    think(
        ctx,
        [
            "basic economy is non-changeable",
            f"booked {r.booked_minutes_ago} min ago, inside the 24h free-cancel window",
            "so cancel-and-rebook is allowed, a direct change is not",
        ],
        ["cancel_booking", "book_flight"],
    )

def run_trajectory(use_think: bool) -> bool:
    label = "with the think tool" if use_think else "no think tool"
    print(f"\n--- Trajectory: {label} ---")
    ctx = Context()

    print(f"  tool_call get_reservation() -> {get_reservation(reservation)}")

    if use_think:
        reflect(ctx, reservation)
        print("  tool_call think() [no-op] checkpoint:")
        for note in ctx.log:
            print(f"     - {note}")
        print("     (think returned nothing; the reasoning is now in context)")

    legal = True
    if ctx.plan:
        print("  agent follows the checkpoint plan")
        for step in ctx.plan:
            if step == "cancel_booking":
                print(f"  tool_call cancel_booking() -> {cancel_booking(reservation)}")
            if step == "book_flight":
                print(f"  tool_call book_flight() -> {book_flight()}")
    else:
        print("  agent acts immediately on the result")
        outcome = change_flight(reservation)
        print(f"  tool_call change_flight() -> {outcome}")
        legal = not outcome.startswith("POLICY VIOLATION")

    print(f"  outcome: {'booking changed legally, violation avoided' if legal else 'illegal change attempted'}")
    return legal

def main() -> None:
    print("=== Structured Reflection (Think Tool) ===")
    print(f"reservation: {get_reservation(reservation)}")
    print("policy: basic economy is non-changeable; 24h free-cancellation window")

    without_think = run_trajectory(False)
    with_think = run_trajectory(True)

    print("\nsummary:")
    print(f"  without think -> {'legal' if without_think else 'policy violation'}")
    print(f"  with think    -> {'legal' if with_think else 'policy violation'}")
    print("  the no-op call added no data and touched no system, but the reasoning it")
    print("  parked in context steered the agent onto a compliant path.")

if __name__ == "__main__":
    main()
```

## References

- Anthropic - The "think" tool: enabling Claude to stop and think in complex agentic environments - https://www.anthropic.com/engineering/claude-think-tool
- tau-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains - https://arxiv.org/abs/2406.12045

---
Source: https://agentic-design.ai/patterns/tool-use/structured-reflection-tool (extraction: free-pack, content sha256 c3095cb6bc36…)
