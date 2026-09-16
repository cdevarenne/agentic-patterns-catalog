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


def test_container_heading_with_h4_children_is_not_emitted(fixtures: Path) -> None:
    d = details.parse_details((fixtures / "page.html").read_text(encoding="utf-8"))
    assert "when_to_use" not in d
    assert d["when_to_use.use_when"] == ["Many handlers exist"]


@pytest.mark.mirror
def test_mirror_templates_yield_expected_keys(mirror: Path) -> None:
    deep = details.parse_details((mirror / "routing" / "capability-routing.html").read_text(encoding="utf-8"))
    assert {"core_mechanism", "workflow_steps", "when_not_to_use", "common_pitfalls", "kpis"} <= set(deep)
    standard = details.parse_details(
        (mirror / "evaluation-monitoring" / "cyberseceval3.html").read_text(encoding="utf-8"))
    assert {"overview_30s", "quick_implementation", "dos_and_donts", "when_to_use.use_when"} <= set(standard)


def test_h4_without_an_h3_in_its_own_section_is_not_keyed_on_a_stale_parent() -> None:
    html = ("<div hidden><h2>Alpha</h2><h3>Workflows</h3><h4>Inner</h4><p>inner item</p>"
            "<h2>Beta</h2><h4>Options</h4><p>option item</p>"
            "<h2>References and Further Reading</h2><p>r</p></div>")
    assert list(details.parse_details(html)) == ["workflows.inner", "options"]
