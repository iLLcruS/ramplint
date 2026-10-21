from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.rules.names import has_accessible_name

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


@rule(
    code="RL301",
    name="heading-order",
    summary="Heading levels must not skip (e.g. <h2> followed by <h4>).",
    wcag="1.3.1 Info and Relationships (A)",
)
def heading_order(root: Node) -> Iterator[tuple[Node, str]]:
    context = root.context
    if context is not None and context.extends_known:
        yield from _heading_order_in_blocks(root, context)
        return
    # Templates are often fragments that start below <h1> (the parent template
    # owns it), so the first heading in a file only sets the baseline.
    previous: int | None = None
    for node in root.iter(*HEADINGS):
        level = int(node.tag[1])
        if previous is not None and level > previous + 1:
            yield (
                node,
                (
                    f"Heading level skips from <h{previous}> to <h{level}>; "
                    f"use <h{previous + 1}> here or restructure the outline"
                ),
            )
        previous = level


@rule(
    code="RL302",
    name="empty-heading",
    summary="Headings must have text content.",
    wcag="2.4.6 Headings and Labels (AA)",
)
def empty_heading(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter(*HEADINGS):
        if node.aria_hidden or has_accessible_name(node):
            continue
        yield node, f"<{node.tag}> is empty; screen reader users navigate by headings"


def _skip_message(previous: str, level: int, previous_level: int) -> str:
    return (
        f"Heading level skips from {previous} to <h{level}>; "
        f"use <h{previous_level + 1}> here or restructure the outline"
    )


def _heading_order_in_blocks(root: Node, context: Any) -> Iterator[tuple[Node, str]]:
    """A child template: its blocks are rendered inside the parent, in the
    parent's order, so headings are compared within each block, and the first
    one with the heading the parent renders before the block."""
    previous: dict[str, int] = {}
    for node in root.iter(*HEADINGS):
        block = context.template.top_block_at(context.template.offset(node.line, node.col))
        if block is None:
            continue  # outside {% block %}: never rendered
        level = int(node.tag[1])
        if block.name not in previous:
            before = context.heading_before(block.name)
            if before not in (None, True) and level > before.level + 1:
                yield node, _skip_message(before.describe(), level, before.level)
        elif level > previous[block.name] + 1:
            yield node, _skip_message(f"<h{previous[block.name]}>", level, previous[block.name])
        previous[block.name] = level
