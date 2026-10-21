from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.rules.names import has_accessible_name, has_naming_attribute


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


@rule(
    code="RL105",
    name="object-alt",
    summary="<object> and <embed> must have a text alternative.",
    wcag="1.1.1 Non-text Content (A)",
)
def object_alt(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("object", "embed"):
        if node.inert or node.dynamic_attrs or node.aria_hidden:
            continue
        if node.role in ("presentation", "none") or has_naming_attribute(node):
            continue
        if node.tag == "object":
            if has_accessible_name(node):
                continue  # fallback content between the tags
            yield (
                node,
                "<object> has no text alternative; add fallback text inside it (for "
                'example a download link) or an aria-label, e.g. aria-label="Price list (PDF)"',
            )
        else:
            yield (
                node,
                "<embed> has no text alternative; add an aria-label or title, e.g. "
                'title="Price list (PDF)"',
            )
