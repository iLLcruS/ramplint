"""A small, forgiving HTML tree built on top of :mod:`html.parser`.

Templates are usually fragments (partials, ``{% block %}`` bodies, includes),
so the tree never fails on unbalanced tags - it just does its best.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from ramplint.template import MARKUP, PLACEHOLDERS, TEXT, BranchPath  # noqa: F401

# fmt: off
VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }
)
# fmt: on

# Opening the key tag implicitly closes any of these if they are open on top
# of the stack (a simplified version of the HTML "optional end tag" rules).
IMPLICIT_CLOSE = {
    "li": frozenset({"li"}),
    "dt": frozenset({"dt", "dd"}),
    "dd": frozenset({"dt", "dd"}),
    "tr": frozenset({"tr", "td", "th"}),
    "td": frozenset({"td", "th"}),
    "th": frozenset({"td", "th"}),
    "thead": frozenset({"tbody", "tfoot", "tr", "td", "th"}),
    "tbody": frozenset({"thead", "tbody", "tfoot", "tr", "td", "th"}),
    "tfoot": frozenset({"thead", "tbody", "tr", "td", "th"}),
    "option": frozenset({"option"}),
    "p": frozenset({"p"}),
}

RAW_TEXT_ELEMENTS = frozenset({"script", "style", "template"})


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    line: int
    col: int
    parent: Node | None = None
    children: list[Node | str] = field(default_factory=list)
    #: True when attributes are generated at render time, e.g.
    #: ``<input {{ widget.attrs }}>`` - we cannot know what they contain.
    dynamic_attrs: bool = False
    #: Which ``{% if %}`` / ``{% for %}`` branch the element is rendered in.
    branch: BranchPath = ()
    #: Attributes whose value in the template source contains ``{{ }}`` or
    #: ``{% %}``, e.g. ``class="{% if active %}on{% endif %}"``.
    templated_attrs: frozenset[str] = frozenset()
    #: Position of the end tag (``(line, col)``), when the element is closed
    #: explicitly. Elements closed implicitly share the end of their parent.
    end: tuple[int, int] | None = None
    #: Cross-template information for the template being linted, set on the
    #: root node only (see :mod:`ramplint.project.context`).
    context: Any = None
    #: The original template source, set on the root node only.
    source: str | None = None

    def contains(self, line: int, col: int) -> bool:
        """``(line, col)`` lies between this element's start and end tags."""
        if self.end is None:
            return False
        return (self.line, self.col) < (line, col) < self.end

    def get(self, name: str, default: str | None = None) -> str | None:
        return self.attrs.get(name, default)

    def has_value(self, name: str) -> bool:
        """The attribute exists and is not blank."""
        value = self.attrs.get(name)
        return value is not None and value.strip() != ""

    def is_dynamic(self, name: str) -> bool:
        """The attribute value is (partly) computed by the template engine."""
        value = self.attrs.get(name)
        if value is None:
            return False
        return name in self.templated_attrs or any(p in value for p in PLACEHOLDERS)

    def iter(self, *tags: str) -> Iterator[Node]:
        """Depth-first iteration over descendants (not including self)."""
        for child in self.children:
            if isinstance(child, Node):
                if not tags or child.tag in tags:
                    yield child
                yield from child.iter(*tags)

    def ancestors(self) -> Iterator[Node]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in RAW_TEXT_ELEMENTS:
                parts.append(child.text())
        return "".join(parts)

    @property
    def role(self) -> str:
        return (self.attrs.get("role") or "").strip().lower()

    @property
    def inert(self) -> bool:
        """Inside a ``<template>`` element: parsed, but not rendered as is."""
        return any(ancestor.tag == "template" for ancestor in self.ancestors())

    @property
    def aria_hidden(self) -> bool:
        return (self.attrs.get("aria-hidden") or "").strip().lower() == "true"

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<{self.tag} at {self.line}:{self.col}>"


# name="value" / name='value' inside a raw start tag.
_RAW_ATTR_RE = re.compile(r"""([^\s"'=<>/`]+)\s*=\s*("[^"]*"|'[^']*')""")


def _templated_attributes(raw_start_tag: str) -> frozenset[str]:
    return frozenset(
        name.lower()
        for name, value in _RAW_ATTR_RE.findall(raw_start_tag)
        if "{%" in value or "{{" in value
    )


class _TreeBuilder(HTMLParser):
    def __init__(
        self,
        branch_of: Callable[[int, int], BranchPath] | None = None,
        source: str | None = None,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.branch_of = branch_of
        self.source = source
        self.line_starts = [0]
        if source is not None:
            self.line_starts += [i + 1 for i, char in enumerate(source) if char == "\n"]
        self.root = Node(tag="#document", attrs={}, line=1, col=1)
        self.stack: list[Node] = [self.root]

    # -- helpers -----------------------------------------------------------
    def _make_node(self, tag: str, attrs: list[tuple[str, str | None]]) -> Node:
        line, offset = self.getpos()
        node = Node(tag=tag, attrs={}, line=line, col=offset + 1)
        if self.branch_of is not None:
            node.branch = self.branch_of(line, offset + 1)
        raw_html = self.get_starttag_text()
        if self.source is not None and raw_html and line <= len(self.line_starts):
            start = self.line_starts[line - 1] + offset
            node.templated_attrs = _templated_attributes(self.source[start : start + len(raw_html)])
        for name, value in attrs:
            if any(p in name for p in PLACEHOLDERS):
                node.dynamic_attrs = True
                continue
            node.attrs.setdefault(name, value if value is not None else "")
        node.parent = self.stack[-1]
        self.stack[-1].children.append(node)
        return node

    # -- HTMLParser hooks --------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        closes = IMPLICIT_CLOSE.get(tag)
        if closes:
            while len(self.stack) > 1 and self.stack[-1].tag in closes:
                self.stack.pop()
        node = self._make_node(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._make_node(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                line, offset = self.getpos()
                for node in self.stack[index:]:
                    node.end = (line, offset + 1)
                del self.stack[index:]
                return
        # Stray end tag (common in partial templates) - ignore it.

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse(
    html: str,
    branch_of: Callable[[int, int], BranchPath] | None = None,
    source: str | None = None,
) -> Node:
    """Parse prepared HTML.

    ``branch_of`` tags each element with its template branch; ``source`` (the
    original template, same geometry as ``html``) lets the parser tell which
    attribute values are built by template tags.
    """
    builder = _TreeBuilder(branch_of, source)
    builder.feed(html)
    builder.close()
    builder.root.source = source
    return builder.root


__all__ = ["Node", "parse", "TEXT", "MARKUP"]
