import pytest

from agentic_patterns_catalog import policy


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
