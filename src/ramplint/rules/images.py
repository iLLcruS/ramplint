from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.aria import effective_role
from ramplint.rules.base import rule
from ramplint.rules.names import has_naming_attribute
from ramplint.template import may_render_markup


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


def _svg_title(svg: Node) -> Node | None:
    return next(
        (child for child in svg.children if isinstance(child, Node) and child.tag == "title"),
        None,
    )


@rule(
    code="RL104",
    name="svg-img-alt",
    summary='<svg role="img"> must have an accessible name.',
    wcag="1.1.1 Non-text Content (A)",
)
def svg_img_alt(root: Node) -> Iterator[tuple[Node, str]]:
    for svg in root.iter("svg"):
        if svg.dynamic_attrs or svg.aria_hidden or effective_role(svg) != "img":
            continue
        if has_naming_attribute(svg):
            continue
        title = _svg_title(svg)
        if title is not None and title.text().strip():
            continue
        if may_render_markup(svg.text()):
            continue  # the <title> may come from {% include %}
        yield (
            svg,
            '<svg role="img"> has no accessible name; add a <title> as its first child or '
            'an aria-label, or use aria-hidden="true" for a decorative icon',
        )
