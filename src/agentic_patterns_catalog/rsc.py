"""Parser for the React Server Components (RSC) stream that Next.js embeds in each page.

Next.js emits `self.__next_f.push([1, "<chunk>"])` script calls. The joined chunks are rows of
`<hexid>:<payload>`. A `T` payload is text: `T<hexlen>,<bytes>`; the length counts UTF-8 bytes and
the text may contain newlines. Other payloads are JSON or reference strings. Parse bytes, not
characters: emoji in a text row shift every later slice otherwise.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.DOTALL)
_ROW_ID = re.compile(rb"([0-9a-f]+):")
_JSON_START = b'[{"0123456789tfn-'


def rsc_text(html: str) -> str:
    """The joined RSC chunks as one string. Each chunk is a JSON string literal."""
    return "".join(json.loads(c) for c in _CHUNK.findall(html))


def rsc_rows(html: str) -> dict[str, Any]:
    """Rows keyed by id. JSON rows are decoded; text and reference rows stay strings."""
    data = rsc_text(html).encode("utf-8")
    decoder = json.JSONDecoder()
    rows: dict[str, Any] = {}
    pos, n = 0, len(data)

    def next_line(p: int) -> int:
        nl = data.find(b"\n", p)
        return n if nl < 0 else nl + 1

    while pos < n:
        m = _ROW_ID.match(data, pos)
        if not m:
            pos = next_line(pos)
            continue
        rid, pos = m.group(1).decode(), m.end()
        if pos >= n:
            break
        head = data[pos:pos + 1]
        if head == b"T":
            comma = data.index(b",", pos)
            length = int(data[pos + 1:comma], 16)
            start = comma + 1
            rows[rid] = data[start:start + length].decode("utf-8", "replace")
            pos = start + length
        elif head in _JSON_START:
            end = data.find(b"\n", pos)
            line = data[pos:(n if end < 0 else end)].decode("utf-8")
            try:
                rows[rid], used = decoder.raw_decode(line)
            except json.JSONDecodeError:
                pos = next_line(pos)
                continue
            pos += len(line[:used].encode("utf-8"))
        else:
            end = data.find(b"\n", pos)
            rows[rid] = data[pos:(n if end < 0 else end)].decode("utf-8", "replace")
            pos = next_line(pos)
            continue
        if pos < n and data[pos:pos + 1] == b"\n":
            pos += 1
    return rows


def find_dicts(node: Any, pred: Callable[[dict[str, Any]], bool]) -> Iterator[dict[str, Any]]:
    """Depth-first: every dict in `node` for which `pred` is true."""
    if isinstance(node, dict):
        if pred(node):
            yield node
        for value in node.values():
            yield from find_dicts(value, pred)
    elif isinstance(node, list):
        for value in node:
            yield from find_dicts(value, pred)


def page_props(html: str) -> dict[str, Any]:
    """The props dict of a pattern page: it carries `tldr` and `selectedTechnique`."""
    rows = rsc_rows(html)
    props = next(find_dicts(rows, lambda d: "tldr" in d and "selectedTechnique" in d), None)
    if props is None:
        raise ValueError("no pattern props (tldr + selectedTechnique) in the RSC stream")
    return props
