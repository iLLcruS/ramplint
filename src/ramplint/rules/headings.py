from __future__ import annotations

from collections.abc import Iterator

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
