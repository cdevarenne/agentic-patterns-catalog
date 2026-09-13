# Agent Skills

Category: tool-use | Complexity: medium

Capabilities packaged as self-contained folders. Each skill is a SKILL.md file with YAML frontmatter (name and description) plus optional scripts and resources. Agents discover skills by their metadata and load them through three levels of progressive disclosure: read name and description to judge relevance, load the full SKILL.md once activated, then execute bundled scripts and resources on demand. This keeps context small while exposing many capabilities, and the format is an open standard adopted across vendors.

## In 30 seconds

- **What:** Packages agent capabilities as self-contained folders with metadata, instructions, and scripts. Agents load only active skill content into context while keeping a lightweight index of all available skills.
- **When:** Agents need access to many tools but limited context window, or when skills must be portable across different agent platforms and vendors.
- **Watch out:** Scripts may fail silently or produce unexpected output if the agent misunderstands skill preconditions or mismatches input formats.

## Key features

- Self-contained folder with SKILL.md, scripts, and resources
- YAML frontmatter metadata (name, description) drives discovery
- Three-level progressive disclosure: metadata, full instructions, bundled files
- Only the active skill's full content enters the context window
- Bundled executable scripts run deterministic work outside the model
- Open, cross-vendor format that is portable between agents

## Use cases

- capability-packaging
- context-efficiency
- reusable-workflows
- tool-bundling
- domain-expertise

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
Setup: the agent has 50 skills installed; only their names and descriptions (~30 tokens each) are in context.

Task: "Fill out this PDF tax form using the values in my notes"

1. Metadata scan: match "PDF form" to the pdf-form skill description
2. Activate: load pdf-form/SKILL.md (full instructions) into context
3. Execute: run the bundled fill_form.py script on the file
4. The deterministic script writes the field values; the model never parses raw PDF bytes

Result: task done while context holds one skill's instructions instead of all 50, so roughly 1.5K tokens are used instead of ~40K
```

## Implementation (python)

```python
#!/usr/bin/env python3

# Agent Skills.
# Skills are self-contained folders (SKILL.md metadata + instructions + a
# bundled script). The agent discovers by metadata, loads one skill's full
# body only when matched, then runs its deterministic script. Context holds
# the active skill, not all installed ones.

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class Skill:
    name: str
    description: str  # Level 1 metadata, always in context
    instructions: str  # Level 2 full SKILL.md body, loaded on activation
    field_map: Dict[str, str]  # bundled resource used by the script
    run: Callable[[Dict[str, str], Dict[str, str]], List[str]]


def words(text: str) -> int:
    return len([w for w in text.split() if w])


# Level 3 script for the pdf-form skill: deterministic field writer. The model
# never parses raw PDF bytes; the bundled script maps notes onto form fields.
def fill_form(field_map: Dict[str, str], notes: Dict[str, str]) -> List[str]:
    lines: List[str] = []
    for form_field, key in field_map.items():
        lines.append(f"  {form_field}: {notes.get(key, '(left blank)')}")
    return lines


def no_op(_field_map: Dict[str, str], _notes: Dict[str, str]) -> List[str]:
    return []


REGISTRY: List[Skill] = [
    Skill(
        "pdf-form",
        "fill PDF form fields from provided values",
        "Read the form field labels, map each label to a note key, then call the "
        "bundled fill_form script to write values without parsing PDF bytes.",
        {"Full Name": "name", "Annual Income": "income", "Filing Status": "status"},
        fill_form,
    ),
    Skill("xlsx-report", "build spreadsheets and pivot tables",
          "Open the workbook, add sheets, and write formatted cells and pivots.", {}, no_op),
    Skill("email-send", "send an email through the outbound gateway",
          "Compose headers and body, then hand off to the mail transport.", {}, no_op),
    Skill("image-resize", "resize and crop raster images",
          "Decode the image, apply the resize filter, and re-encode.", {}, no_op),
]


def main() -> None:
    print("Agent Skills, three-level progressive disclosure\n")

    task = "Fill out this PDF tax form using the values in my notes"
    notes = {"name": "Dana Lee", "income": "48,000", "status": "single"}
    print(f"Task: {task}")
    print(f"Installed skills: {', '.join(s.name for s in REGISTRY)}\n")

    # Level 1: scan only names and descriptions to judge relevance. Score each
    # skill by how many of its description keywords appear in the task.
    print("Level 1 discover: scan metadata (name + description) only")
    task_words = set(task.lower().split())
    chosen: Optional[Skill] = None
    best_score = 0
    for skill in REGISTRY:
        keywords = [w for w in skill.description.lower().split() if len(w) >= 3]
        score = sum(1 for w in keywords if w in task_words)
        print(f'  {skill.name:<12} "{skill.description}" -> score {score}')
        if score > best_score:
            best_score = score
            chosen = skill
    if chosen is None:
        print("No skill matched; answering without one.")
        return
    print(f"  best match: {chosen.name}")

    # Level 2: activate the matched skill, loading its full SKILL.md body.
    print(f"\nLevel 2 activate: load {chosen.name}/SKILL.md full instructions")
    print(f"  {chosen.instructions}")

    # Level 3: execute the bundled deterministic script over bundled resources.
    print("\nLevel 3 execute: run bundled fill_form script with field-map resource")
    filled = chosen.run(chosen.field_map, notes)
    print("Filled form:")
    for line in filled:
        print(line)

    # Context budget: metadata for all skills + one full skill, versus loading
    # every skill in full. Estimated in whitespace-separated tokens.
    meta_all = sum(words(s.name) + words(s.description) for s in REGISTRY)
    full_chosen = words(chosen.instructions)
    used = meta_all + full_chosen
    if_all_full = sum(words(s.name) + words(s.description) + words(s.instructions) for s in REGISTRY)
    print("\nContext budget (estimated tokens):")
    print(f"  metadata for all {len(REGISTRY)} skills: {meta_all}")
    print(f"  + full body of {chosen.name} only        : {full_chosen}")
    print(f"  = used                                    : {used}")
    print(f"  vs loading every skill in full            : {if_all_full}")
    print(f"\nOnly 1 of {len(REGISTRY)} skills loaded fully; context stayed small.")


if __name__ == "__main__":
    main()
```

## References

- Anthropic - Equipping agents for the real world with Agent Skills - https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Agent Skills open specification and directory - https://agentskills.io/home

---
Source: https://agentic-design.ai/patterns/tool-use/agent-skills (extraction: free-pack, content sha256 8ea17ebf320b…)
