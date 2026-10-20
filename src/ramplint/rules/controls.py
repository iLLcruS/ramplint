from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.rules.names import has_accessible_name, has_naming_attribute


@rule(
    code="RL501",
    name="button-name",
    summary="Buttons must have an accessible name.",
    wcag="4.1.2 Name, Role, Value (A)",
)
def button_name(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter():
        if node.dynamic_attrs:
            continue

        if node.tag == "input":
            if (node.get("type") or "").strip().lower() != "button":
                continue  # submit/reset get a default name from the browser
            if node.has_value("value") or has_naming_attribute(node):
                continue
            yield node, '<input type="button"> needs a non-empty value attribute'

        elif node.tag == "button" or (node.role == "button" and node.tag != "a"):
            if has_accessible_name(node):
                continue
            element = "<button>" if node.tag == "button" else f'<{node.tag} role="button">'
            yield (
                node,
                (
                    f"{element} has no accessible name; add text or an "
                    "aria-label (icon-only buttons need one)"
                ),
            )


@rule(
    code="RL502",
    name="link-name",
    summary="Links must have an accessible name.",
    wcag="2.4.4 Link Purpose (A), 4.1.2 Name, Role, Value (A)",
)
def link_name(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("a"):
        if node.get("href") is None or node.dynamic_attrs:
            continue
        if has_accessible_name(node):
            continue
        yield (
            node,
            (
                "<a> link has no accessible name; add text, an aria-label, or alt "
                "text on the image inside it"
            ),
        )
