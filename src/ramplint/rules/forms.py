from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.rules.names import has_naming_attribute
from ramplint.template import PLACEHOLDERS

#: Input types that are not labelled with <label> (or are not visible).
UNLABELLED_INPUT_TYPES = frozenset({"hidden", "submit", "button", "reset", "image"})


def _describe(node: Node) -> str:
    if node.tag == "input":
        return f'<input type="{(node.get("type") or "text").strip()}">'
    return f"<{node.tag}>"


@rule(
    code="RL401",
    name="form-label",
    summary="Form controls must have an associated <label>.",
    wcag="1.3.1 Info and Relationships (A), 4.1.2 Name, Role, Value (A)",
)
def form_label(root: Node) -> Iterator[tuple[Node, str]]:
    labels = list(root.iter("label"))
    label_targets = {label.get("for", "").strip() for label in labels if label.has_value("for")}
    has_dynamic_label_target = any(label.is_dynamic("for") for label in labels)

    for node in root.iter("input", "select", "textarea"):
        if node.dynamic_attrs or "hidden" in node.attrs:
            continue
        if node.tag == "input":
            input_type = (node.get("type") or "text").strip().lower()
            if input_type in UNLABELLED_INPUT_TYPES or any(p in input_type for p in PLACEHOLDERS):
                continue

        if has_naming_attribute(node):
            continue
        if any(ancestor.tag == "label" for ancestor in node.ancestors()):
            continue

        element_id = (node.get("id") or "").strip()
        if element_id:
            if node.is_dynamic("id") or has_dynamic_label_target:
                continue  # cannot be resolved statically - stay quiet
            if element_id in label_targets:
                continue
            hint = f'add <label for="{element_id}">'
        else:
            hint = "add an id and a matching <label for>, or wrap it in a <label>"

        if node.has_value("placeholder"):
            hint += " (a placeholder is not a label)"
        yield node, f"{_describe(node)} has no associated label; {hint}"
