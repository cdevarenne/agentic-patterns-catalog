from pathlib import Path

import pytest

from agentic_patterns_catalog import rsc


def test_rows_decode_json_and_text_rows(fixtures: Path) -> None:
    rows = rsc.rsc_rows((fixtures / "page.html").read_text(encoding="utf-8"))
    assert rows["2"] == "Hello 🌍!!"          # T row, byte length, emoji
    assert rows["3"][1] == "div"               # JSON row after the text row is intact
    assert rows["1"].startswith("HL[")         # reference row kept as text


def test_page_props_finds_tldr_and_technique(fixtures: Path) -> None:
    props = rsc.page_props((fixtures / "page.html").read_text(encoding="utf-8"))
    assert props["selectedTechnique"]["id"] == "fixture-routing"
    assert props["tldr"]["what"].startswith("Matches")
    assert len(props["categories"]) == 1


def test_page_props_raises_without_props() -> None:
    with pytest.raises(ValueError, match="no pattern props"):
        rsc.page_props("<html><script>self.__next_f.push([1,\"1:[]\\n\"])</script></html>")


@pytest.mark.mirror
def test_every_mirrored_page_has_props(mirror: Path) -> None:
    pages = sorted(mirror.glob("*/*.html"))
    assert len(pages) == 288
    for page in pages:
        props = rsc.page_props(page.read_text(encoding="utf-8"))
        assert props["selectedTechnique"]["id"] == page.stem
        assert props["selectedTechnique"]["category"] == page.parent.name
        assert len(props["categories"]) == 24
