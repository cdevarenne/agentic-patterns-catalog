from pathlib import Path

import pytest

from agentic_patterns_catalog import details


def test_normalize_heading() -> None:
    assert details.normalize_heading("KPIs / Success Metrics") == "kpis"
    assert details.normalize_heading("Do's & Don'ts") == "dos_and_donts"
    assert details.normalize_heading("30-Second Overview") == "overview_30s"
    assert details.normalize_heading("When NOT to Use") == "when_not_to_use"
    assert details.normalize_heading("Workflow / Steps") == "workflow_steps"


def test_parse_fixture_covers_li_p_span_and_h4(fixtures: Path) -> None:
    d = details.parse_details((fixtures / "page.html").read_text(encoding="utf-8"))
    assert d["core_mechanism"] == ["Matches capability to request."]
    assert d["workflow_steps"] == ["Analyze the request.", "Match a handler."]
    assert d["key_features"] == ["Registry of handler capabilities"]
    assert d["when_to_use.use_when"] == ["Many handlers exist"]      # bullet stripped
    assert d["when_to_use.avoid_when"] == ["One handler only"]
    assert "references_and_further_reading" not in d


def test_page_without_details_block_gives_empty_dict() -> None:
    assert details.parse_details("<html><body><p>x</p></body></html>") == {}


@pytest.mark.mirror
def test_mirror_templates_yield_expected_keys(mirror: Path) -> None:
    deep = details.parse_details((mirror / "routing" / "capability-routing.html").read_text(encoding="utf-8"))
    assert {"core_mechanism", "workflow_steps", "when_not_to_use", "common_pitfalls", "kpis"} <= set(deep)
    standard = details.parse_details(
        (mirror / "evaluation-monitoring" / "cyberseceval3.html").read_text(encoding="utf-8"))
    assert {"overview_30s", "quick_implementation", "dos_and_donts", "when_to_use.use_when"} <= set(standard)
