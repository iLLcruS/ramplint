from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.template import may_render_markup, mutually_exclusive


def template_ids(root: Node) -> dict[str, Node | None] | None:
    """Ids on the rendered page, mapped to their element in this template.

    None when some ids may come from markup that cannot be read: an
    unresolvable ``{% include %}``, the template this one extends, a rendered
    form field or a dynamic ``id``.
    """
    own: dict[str, Node | None] = {}
    for node in root.iter():
        if node.dynamic_attrs or node.is_dynamic("id"):
            return None
        element_id = (node.get("id") or "").strip()
        if element_id:
            own.setdefault(element_id, node)
    context = root.context
    if context is not None:
        others = context.ids_with_includes()
        if others is None:
            return None
        return {**dict.fromkeys(others), **own}
    if may_render_markup(root.text()):
        return None
    return own


def rendered_elements(root: Node) -> Iterator[Node]:
    """Elements that end up in the document (skips inert ``<template>`` content)."""
    for child in root.children:
        if isinstance(child, Node):
            yield child
            if child.tag != "template":
                yield from rendered_elements(child)


@rule(
    code="RL303",
    name="duplicate-id",
    summary="id attributes must be unique within a template.",
    wcag="1.3.1 Info and Relationships (A), 4.1.1 Parsing (WCAG 2.0/2.1)",
)
def duplicate_id(root: Node) -> Iterator[tuple[Node, str]]:
    seen: dict[str, list[Node]] = {}
    for node in rendered_elements(root):
        if node.is_dynamic("id"):
            continue
        element_id = (node.get("id") or "").strip()
        if not element_id:
            continue

        previous = seen.setdefault(element_id, [])
        # Same id in {% if %} / {% else %} branches is fine: only one renders.
        clash = next(
            (other for other in previous if not mutually_exclusive(other.branch, node.branch)),
            None,
        )
        previous.append(node)
        if clash is None:
            continue
        yield (
            node,
            f'Duplicate id "{element_id}" (first used on line {clash.line}); '
            "ids must be unique for labels and ARIA references to work",
        )
