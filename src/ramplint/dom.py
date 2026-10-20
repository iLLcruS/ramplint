"""A small, forgiving HTML tree built on top of :mod:`html.parser`.

Templates are usually fragments (partials, ``{% block %}`` bodies, includes),
so the tree never fails on unbalanced tags - it just does its best.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser

from ramplint.template import MARKUP, PLACEHOLDERS, TEXT  # noqa: F401

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

    def get(self, name: str, default: str | None = None) -> str | None:
        return self.attrs.get(name, default)

    def has_value(self, name: str) -> bool:
        """The attribute exists and is not blank."""
        value = self.attrs.get(name)
        return value is not None and value.strip() != ""

    def is_dynamic(self, name: str) -> bool:
        value = self.attrs.get(name)
        return value is not None and any(p in value for p in PLACEHOLDERS)

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
    def aria_hidden(self) -> bool:
        return (self.attrs.get("aria-hidden") or "").strip().lower() == "true"

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<{self.tag} at {self.line}:{self.col}>"


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node(tag="#document", attrs={}, line=1, col=1)
        self.stack: list[Node] = [self.root]

    # -- helpers -----------------------------------------------------------
    def _make_node(self, tag: str, attrs: list[tuple[str, str | None]]) -> Node:
        line, offset = self.getpos()
        node = Node(tag=tag, attrs={}, line=line, col=offset + 1)
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
                del self.stack[index:]
                return
        # Stray end tag (common in partial templates) - ignore it.

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


__all__ = ["Node", "parse", "TEXT", "MARKUP"]
