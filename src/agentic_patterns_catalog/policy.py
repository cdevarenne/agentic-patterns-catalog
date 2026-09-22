"""Authorization decision point. `AllowlistPDP` is the default; `OpaPDP` queries an external OPA server."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
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


OPA_DECISION_PATH = "/v1/data/catalog/authz/decision"
DEFAULT_OPA_URL = "http://localhost:8181"


class OpaPDP:
    """Asks a local OPA. Fails closed: no answer, a malformed answer or an unreachable server is a deny."""

    def __init__(self, url: str = DEFAULT_OPA_URL, access: str | None = None, timeout: float = 2.0) -> None:
        if isinstance(access, (int, float)):
            timeout = access
            access = None
        self.url = url.rstrip("/") + OPA_DECISION_PATH
        self.access = access
        self.timeout = timeout

    def decide(self, subject: str, tool: str, args: dict[str, Any]) -> Decision:
        body = json.dumps({"input": {"subject": subject, "tool": tool, "args": args}}).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read()).get("result")
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            return Decision(False, f"OPA unreachable: {e}", None)
        if not isinstance(result, dict) or "allow" not in result:
            return Decision(False, "OPA returned no decision", None)
        return Decision(bool(result["allow"]), str(result.get("reason", "")), result.get("role"))


def pdp_from_env(env: Mapping[str, str]) -> PolicyDecisionPoint:
    """`CATALOG_PDP=allowlist` (default) or `opa`. Any other value is a ValueError."""
    kind = env.get("CATALOG_PDP", "allowlist")
    if kind == "allowlist":
        return AllowlistPDP(env.get("CATALOG_ACCESS", ""))
    if kind == "opa":
        return OpaPDP(env.get("OPA_URL", DEFAULT_OPA_URL))
    raise ValueError(f"CATALOG_PDP={kind!r}; known: allowlist, opa")

