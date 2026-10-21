from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.template import mutually_exclusive


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
