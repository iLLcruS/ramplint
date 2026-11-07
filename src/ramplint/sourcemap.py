"""Template source maps: which template line produced an element of a page.

:func:`annotate` adds ``data-rl-src="<path>:<line>:<col>"`` to every start tag of
a Django template before Django compiles it (see :mod:`ramplint.django`). The
positions come from :func:`ramplint.template.prepare`, so they are exactly the
positions the template linter reports. Tags inside ``<script>`` and ``<style>``,
attribute values, comments and ``{% verbatim %}`` blocks are left alone.

The browser scan reads the attribute back, removes it before any rule sees the
page, and reports problems at the template location.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from html.parser import HTMLParser

from ramplint.template import prepare

#: Attribute that carries the template location of an element.
SOURCE_ATTRIBUTE = "data-rl-src"
_VERBATIM_RE = re.compile(r"\{%-?\s*verbatim\b.*?%\}.*?\{%-?\s*endverbatim\s*-?%\}", re.DOTALL)
_LOCATION_RE = re.compile(r"^(?P<path>.+):(?P<line>\d+):(?P<col>\d+)$")


class _StartTags(HTMLParser):
    """Offsets where an attribute can be inserted into each start tag."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self.line_starts = [0, *(i + 1 for i, char in enumerate(text) if char == "\n")]
        #: ``(insert offset, line, col)``.
        self.found: list[tuple[int, int, int]] = []

    def _record(self) -> None:
        raw = self.get_starttag_text() or ""
        line, offset = self.getpos()
        if SOURCE_ATTRIBUTE in raw:
            return
        start = self.line_starts[line - 1] + offset
        end = start + len(raw) - (2 if raw.endswith("/>") else 1)
        self.found.append((end, line, offset + 1))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record()


def annotate(source: str, path: str) -> str:
    """``source`` with ``data-rl-src="path:line:col"`` on every start tag."""
    prepared = prepare(source).html  # same length and lines as ``source``
    parser = _StartTags(prepared)
    parser.feed(prepared)
    parser.close()
    skipped = [(m.start(), m.end()) for m in _VERBATIM_RE.finditer(source)]
    starts = [start for start, _ in skipped]
    pieces: list[str] = []
    position = 0
    for offset, line, col in parser.found:
        index = bisect_right(starts, offset) - 1
        if index >= 0 and skipped[index][0] <= offset < skipped[index][1]:
            continue
        pieces.append(source[position:offset])
        pieces.append(f' {SOURCE_ATTRIBUTE}="{path}:{line}:{col}"')
        position = offset
    pieces.append(source[position:])
    return "".join(pieces)


def parse_location(value: str | None) -> tuple[str, int, int] | None:
    """``("catalog/list.html", 14, 9)`` from ``catalog/list.html:14:9``."""
    match = _LOCATION_RE.match(value or "")
    if match is None:
        return None
    return match.group("path"), int(match.group("line")), int(match.group("col"))
