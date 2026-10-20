from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule


@rule(
    code="RL601",
    name="html-lang",
    summary="The <html> element must declare the page language.",
    wcag="3.1.1 Language of Page (A)",
)
def html_lang(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("html"):
        if node.dynamic_attrs or node.has_value("lang"):
            continue
        yield (
            node,
            (
                '<html> is missing a lang attribute; add e.g. lang="en" or '
                'lang="{{ LANGUAGE_CODE }}"'
            ),
        )
