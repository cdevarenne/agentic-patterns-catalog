# Computer Use

Category: tool-use | Complexity: high

Agents operate graphical user interfaces (desktop, browser, or mobile) the way a person does, by reading screenshots and issuing mouse and keyboard actions instead of calling APIs. The core challenge is GUI grounding: mapping an intent to exact pixel coordinates on the screen. The agent runs a loop of screenshot, reason, act, and observe until the task is complete.

## In 30 seconds

- **What:** Agent reads screenshots, grounds intent to pixel coordinates, executes mouse and keyboard actions, loops until task completion.
- **When:** Systems with no API, complex multi-step UI workflows, or when you need to automate legacy or third-party applications.
- **Watch out:** GUI grounding fails on dynamic layouts, small targets, or obstructed elements, causing cascading errors that are hard to recover from.

## Key features

- Screenshot-based perception of the live screen
- GUI grounding from intent to precise pixel coordinates
- Low-level action space: click, type, scroll, drag, key press
- Perception-reason-act-observe loop with feedback after each step
- Error recovery from popups, modals, and unexpected UI states
- Works on applications and sites that expose no API

## Use cases

- gui-automation
- browser-agents
- legacy-app-integration
- rpa
- qa-testing

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Task: "Book the cheapest morning flight from SFO to JFK on July 20"

Agent Loop:
1. Screenshot: airline home page
2. Ground + act: click the "From" field, type "SFO"; click "To", type "JFK"
3. Screenshot: date picker is open -> click July 20
4. Act: click Search
5. Observe: results load, but a newsletter popup now covers the page
6. Error recovery: locate and click the popup close (x) button
7. Ground: sort by "Departure: earliest", read prices from the pixels
8. Act: click the 7:05 AM result, then Continue

Result: correct flight selected with no airline API, driven only by screenshots and clicks
```

## Implementation (python)

```python
#!/usr/bin/env python3
# Computer Use: an agent drives a GUI it can only perceive as screenshots.
# Each cycle it takes a screenshot (a text grid of labeled elements), grounds
# an intent to pixel coordinates, clicks, then observes whether the screen
# changed as expected, recovering from an unexpected consent popup.

from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class Element:
    label: str
    col: int
    row: int

@dataclass
class Screenshot:
    screen: str
    popup: bool
    elements: List[Element]

class Desktop:
    def __init__(self) -> None:
        self.screen = "home"
        self.popup_open = True
        self.dark_mode = False

    def screenshot(self) -> Screenshot:
        if self.popup_open:
            return Screenshot(self.screen, True, [
                Element("Consent: Accept", 1, 1),
                Element("Consent: Decline", 2, 1),
            ])
        if self.screen == "home":
            return Screenshot("home", False, [
                Element("Settings", 0, 2),
                Element("Profile", 2, 2),
            ])
        if self.screen == "settings":
            return Screenshot("settings", False, [
                Element("General", 0, 1),
                Element("Appearance", 1, 1),
            ])
        label = "Dark Mode: ON" if self.dark_mode else "Dark Mode: OFF"
        return Screenshot("appearance", False, [Element(label, 1, 1)])

    # A click lands at pixel coords; the element nearest those pixels reacts.
    def click_at(self, x: int, y: int, shot: Screenshot) -> None:
        hit = nearest(shot.elements, x, y)
        if hit is None:
            return
        if hit.label.startswith("Consent:"):
            self.popup_open = False
        elif hit.label == "Settings":
            self.screen = "settings"
        elif hit.label == "Appearance":
            self.screen = "appearance"
        elif hit.label.startswith("Dark Mode"):
            self.dark_mode = not self.dark_mode

def px(el: Element) -> Tuple[int, int]:
    return (el.col * 100 + 50, el.row * 60 + 30)

def nearest(els: List[Element], x: int, y: int) -> Optional[Element]:
    best: Optional[Element] = None
    best_d = 10 ** 9
    for el in els:
        ex, ey = px(el)
        d = abs(ex - x) + abs(ey - y)
        if d < best_d:
            best_d, best = d, el
    return best

def ground(shot: Screenshot, want: str) -> Optional[Tuple[int, int]]:
    for el in shot.elements:
        if el.label == want:
            return px(el)
    return None

def render_grid(shot: Screenshot) -> str:
    lines: List[str] = []
    for r in range(4):
        parts: List[str] = []
        for c in range(3):
            text = "."
            for el in shot.elements:
                if el.col == c and el.row == r:
                    text = el.label
            parts.append(text.ljust(18)[:18])
        joined = "|".join(parts)
        if joined.replace(".", "").replace("|", "").strip():
            lines.append("    " + joined)
    return "\n".join(lines)

# Model stub: pick the next action purely from what the screenshot shows.
def decide(shot: Screenshot) -> Tuple[str, str]:
    if shot.popup:
        return ("click", "Consent: Accept")
    if shot.screen == "home":
        return ("click", "Settings")
    if shot.screen == "settings":
        return ("click", "Appearance")
    if shot.elements and shot.elements[0].label == "Dark Mode: OFF":
        return ("click", "Dark Mode: OFF")
    return ("done", "")

def main() -> None:
    desk = Desktop()
    print("Task: enable dark mode in the Settings app (screenshots + clicks only)\n")
    for cycle in range(1, 9):
        shot = desk.screenshot()
        print(f"--- cycle {cycle} ---")
        print(f"[screenshot] screen={shot.screen} popup={'OPEN' if shot.popup else 'none'}")
        print(render_grid(shot))
        action, label = decide(shot)
        if action == "done":
            print("[reason] dark mode is ON; goal reached, stopping.\n")
            print("Result: dark mode enabled with no API, only screenshot -> ground -> click -> observe.")
            return
        reason = ("a consent popup is blocking the UI; dismiss it before continuing"
                  if shot.popup else f'advance toward the Dark Mode toggle by clicking "{label}"')
        print(f"[reason] {reason}")
        coords = ground(shot, label)
        if coords is None:
            print("[ground] target not found, retry")
            continue
        print(f'[ground] "{label}" -> pixel {coords}')
        before = str(desk.screenshot())
        desk.click_at(coords[0], coords[1], shot)
        after = str(desk.screenshot())
        print(f"[act] click {coords}")
        print(f"[observe] screen changed: {'yes' if before != after else 'no'}\n")
    print("Result: stopped after max cycles.")

if __name__ == "__main__":
    main()
```

## References

- Anthropic - Computer use tool - https://docs.claude.com/en/docs/agents-and-tools/computer-use
- OpenAI - Computer-Using Agent (CUA) - https://openai.com/index/computer-using-agent/
- OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments - https://os-world.github.io/
- UI-TARS: Pioneering Automated GUI Interaction with Native Agents - https://arxiv.org/abs/2501.12326

---
Source: https://agentic-design.ai/patterns/tool-use/computer-use (extraction: free-pack, content sha256 b965973dcb7c…)
