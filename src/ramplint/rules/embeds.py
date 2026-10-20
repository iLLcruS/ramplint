from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.rules.names import has_naming_attribute


@rule(
    code="RL102",
    name="iframe-title",
    summary="Frames must have a title describing their content.",
    wcag="4.1.2 Name, Role, Value (A)",
)
def iframe_title(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("iframe", "frame"):
        if node.dynamic_attrs or node.aria_hidden:
            continue
        if has_naming_attribute(node):
            continue
        yield (
            node,
            f"<{node.tag}> is missing a title; describe its content, "
            'e.g. title="Store location map"',
        )
