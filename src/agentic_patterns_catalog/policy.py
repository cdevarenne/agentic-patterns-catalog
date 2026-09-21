"""Authorization decision point. `AllowlistPDP` is the default; `OpaPDP` arrives with the policy layer."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

READ_TOOLS = frozenset({"list_categories", "search_patterns", "get_pattern", "get_example", "select"})
TOOLS_BY_ROLE: dict[str, frozenset[str]] = {
    "reader": READ_TOOLS,
    "curator": READ_TOOLS | {"put_pattern"},
}
LOCAL_SUBJECT = "stdio-local"


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str
    role: str | None


class PolicyDecisionPoint(Protocol):
    def decide(self, subject: str, tool: str, args: dict[str, Any]) -> Decision: ...


def parse_access(access: str) -> dict[str, str]:
    """`"a@x.com:curator,b@y.com:reader"` → `{subject: role}`. Empty string → `{}`."""
    roles: dict[str, str] = {}
    for entry in filter(None, (e.strip() for e in access.split(","))):
        subject, sep, role = entry.partition(":")
        if not sep or not subject or not role:
            raise ValueError(f"CATALOG_ACCESS entry {entry!r} is not SUBJECT:ROLE")
        if role not in TOOLS_BY_ROLE:
            raise ValueError(f"unknown role {role!r} for {subject!r}; known: {', '.join(sorted(TOOLS_BY_ROLE))}")
        roles[subject] = role
    return roles


class AllowlistPDP:
    """Subject → role from an access string (argument, else `CATALOG_ACCESS`). Local stdio is a curator."""

    def __init__(self, access: str | None = None) -> None:
        self.roles = parse_access(access if access is not None else os.environ.get("CATALOG_ACCESS", ""))

    def decide(self, subject: str, tool: str, args: dict[str, Any]) -> Decision:
        role = "curator" if subject == LOCAL_SUBJECT else self.roles.get(subject)
        if role is None:
            return Decision(False, f"{subject!r} is not in the allowlist", None)
        if tool not in TOOLS_BY_ROLE[role]:
            return Decision(False, f"role {role!r} may not call {tool!r}", role)
        return Decision(True, f"role {role!r} may call {tool!r}", role)
