import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from agentic_patterns_catalog import policy

POLICY_DIR = Path(__file__).resolve().parents[1] / "policy"


def test_parse_access_string() -> None:
    pdp = policy.AllowlistPDP("a@x.com:curator, b@y.com:reader")
    assert pdp.roles == {"a@x.com": "curator", "b@y.com": "reader"}


def test_malformed_access_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="CATALOG_ACCESS"):
        policy.AllowlistPDP("a@x.com")
    with pytest.raises(ValueError, match="role"):
        policy.AllowlistPDP("a@x.com:admin")


def test_env_is_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALOG_ACCESS", "c@z.com:reader")
    assert policy.AllowlistPDP().roles == {"c@z.com": "reader"}
    monkeypatch.delenv("CATALOG_ACCESS")
    assert policy.AllowlistPDP().roles == {}


@pytest.mark.parametrize(
    ("subject", "tool", "allow"),
    [
        ("stdio-local", "put_pattern", True),
        ("a@x.com", "put_pattern", True),
        ("b@y.com", "put_pattern", False),
        ("b@y.com", "select", True),
        ("nobody@x.com", "select", False),
        ("a@x.com", "drop_everything", False),
    ],
)
def test_decide_matrix(subject: str, tool: str, allow: bool) -> None:
    pdp = policy.AllowlistPDP("a@x.com:curator,b@y.com:reader")
    d = pdp.decide(subject, tool, {})
    assert d.allow is allow
    assert d.reason


def test_decision_names_the_role() -> None:
    d = policy.AllowlistPDP("a@x.com:curator").decide("a@x.com", "select", {})
    assert d.role == "curator"
    assert policy.AllowlistPDP().decide("x@x.com", "select", {}).role is None


def _opa_stub(response: bytes | None, status: int = 200):
    """A one-route HTTP server that answers every POST with `response` (None = connection refused)."""
    seen: list[dict] = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(status)
            self.end_headers()
            self.wfile.write(response or b"")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}", seen


def test_opa_pdp_posts_the_input_and_reads_the_decision() -> None:
    srv, url, seen = _opa_stub(b'{"result": {"allow": true, "reason": "ok", "role": "reader"}}')
    try:
        d = policy.OpaPDP(url).decide("b@y.com", "select", {"task": "x"})
    finally:
        srv.shutdown()
    assert d == policy.Decision(True, "ok", "reader")
    assert seen == [{"input": {"subject": "b@y.com", "tool": "select", "args": {"task": "x"}}}]


def test_opa_pdp_denies_on_missing_result_and_on_unreachable_server() -> None:
    srv, url, _ = _opa_stub(b"{}")
    try:
        d = policy.OpaPDP(url).decide("b@y.com", "select", {})
    finally:
        srv.shutdown()
    assert d.allow is False and "no decision" in d.reason
    dead = policy.OpaPDP("http://127.0.0.1:9").decide("b@y.com", "select", {})
    assert dead.allow is False and "unreachable" in dead.reason


def test_pdp_from_env_picks_the_implementation() -> None:
    assert isinstance(policy.pdp_from_env({}), policy.AllowlistPDP)
    assert isinstance(policy.pdp_from_env({"CATALOG_PDP": "opa"}), policy.OpaPDP)
    with pytest.raises(ValueError, match="CATALOG_PDP"):
        policy.pdp_from_env({"CATALOG_PDP": "ldap"})


def opa_bin() -> str | None:
    """`opa` on PATH, else `$OPA_BIN` when it points at an executable, else None."""
    found = shutil.which("opa")
    if found:
        return found
    candidate = os.environ.get("OPA_BIN")
    return candidate if candidate and os.access(candidate, os.X_OK) else None


needs_opa = pytest.mark.skipif(opa_bin() is None, reason="opa not on PATH and OPA_BIN unset")


@needs_opa
def test_opa_unit_tests_pass() -> None:
    subprocess.run([opa_bin(), "test", str(POLICY_DIR)], check=True, capture_output=True)


@needs_opa
@pytest.mark.parametrize(
    ("subject", "tool"),
    [
        (s, t)
        for s in ("stdio-local", "a@x.com", "b@y.com", "nobody@x.com")
        for t in ("select", "get_pattern", "put_pattern", "drop_everything")
    ],
)
def test_rego_agrees_with_the_allowlist(subject: str, tool: str, tmp_path: Path) -> None:
    access = "a@x.com:curator,b@y.com:reader"
    expected = policy.AllowlistPDP(access).decide(subject, tool, {})
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"catalog": {"access": policy.parse_access(access)}}))
    inp = tmp_path / "input.json"
    inp.write_text(json.dumps({"subject": subject, "tool": tool, "args": {}}))
    out = subprocess.run(
        [
            opa_bin(),
            "eval",
            "-f",
            "json",
            "-d",
            str(POLICY_DIR),
            "-d",
            str(data),
            "-i",
            str(inp),
            "data.catalog.authz.decision",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    got = json.loads(out)["result"][0]["expressions"][0]["value"]
    assert (got["allow"], got["role"]) == (expected.allow, expected.role)
