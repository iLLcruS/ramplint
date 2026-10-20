from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.rules.names import has_naming_attribute


@rule(
    code="RL101",
    name="img-alt",
    summary="Images must have an alt attribute.",
    wcag="1.1.1 Non-text Content (A)",
)
def img_alt(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("img", "area", "input"):
        if node.dynamic_attrs:
            continue

        if node.tag == "img":
            if (
                "alt" in node.attrs
                or node.has_value("aria-label")
                or node.has_value("aria-labelledby")
            ):
                continue
            yield node, '<img> is missing an alt attribute (use alt="" for decorative images)'

        elif node.tag == "area":
            if node.get("href") is None or node.has_value("alt") or has_naming_attribute(node):
                continue
            yield node, "<area> in an image map needs a non-empty alt attribute"

        elif (node.get("type") or "").strip().lower() == "image":
            if node.has_value("alt") or has_naming_attribute(node):
                continue
            yield node, '<input type="image"> needs a non-empty alt attribute describing the action'
