"""Parser for the per-pattern detail sections streamed as a hidden HTML block."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

_HEADINGS = ("h2", "h3", "h4")
_ALIASES = {
    "kpis_success_metrics": "kpis",
    "do_s_and_don_ts": "dos_and_donts",
    "30_second_overview": "overview_30s",
}
_STOP = "references_and_further_reading"
_MIN_LEAF_TEXT = 15


def normalize_heading(text: str) -> str:
    """`KPIs / Success Metrics` → `kpis`; `Do's & Don'ts` → `dos_and_donts`."""
    key = text.lower().replace("&", " and ")
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    return _ALIASES.get(key, key)


def _clean(text: str) -> str:
    return re.sub(r"^[•\-–—*]\s*", "", " ".join(text.split())).strip()


def _segment(heading: Tag) -> list[Tag]:
    """Tags after `heading` up to the next heading of any level."""
    out: list[Tag] = []
    for node in heading.next_elements:
        if isinstance(node, Tag) and node.name in _HEADINGS:
            break
        if isinstance(node, Tag):
            out.append(node)
    return out


def _items(segment: list[Tag]) -> list[str]:
    """Texts of li/p in the segment; else texts of leaf span/div that look like items."""
    primary = [_clean(t.get_text(" ", strip=True)) for t in segment if t.name in ("li", "p")]
    primary = [t for t in primary if t]
    if primary:
        return list(dict.fromkeys(primary))
    leaves = [
        _clean(t.get_text(" ", strip=True))
        for t in segment
        if t.name in ("span", "div") and not t.find_all(True) and len(t.get_text(strip=True)) >= _MIN_LEAF_TEXT
    ]
    return list(dict.fromkeys(t for t in leaves if t))


def _details_block(soup: BeautifulSoup) -> Tag | None:
    for block in soup.find_all("div", hidden=True):
        if any(normalize_heading(h.get_text(" ", strip=True)) == _STOP for h in block.find_all("h2")):
            return block
    return None


def parse_details(html: str) -> dict[str, list[str]]:
    """`{normalized heading: [items]}` for the hidden details block; `{}` when a page has none."""
    soup = BeautifulSoup(html, "html.parser")
    block = _details_block(soup)
    if block is None:
        return {}
    out: dict[str, list[str]] = {}
    parent_key: dict[int, str] = {}
    for heading in block.find_all(_HEADINGS):
        level = int(heading.name[1])
        key = normalize_heading(heading.get_text(" ", strip=True))
        if key == _STOP:
            break
        # A new heading closes every heading at its level or deeper. Without this, an h4 in a
        # later section keeps the h3 of an earlier section as its parent.
        for open_level in [lvl for lvl in parent_key if lvl >= level]:
            del parent_key[open_level]
        parent_key[level] = key
        if level == 4 and 3 in parent_key:
            key = f"{parent_key[3]}.{key}"
        items = _items(_segment(heading))
        if items and key not in out:
            out[key] = items
    return out
