"""Helpers that approximate the accessible name computation.

This is intentionally simpler than the full W3C algorithm: we only need to
answer "does this element have *any* name", and we must stay on the safe
side when template placeholders make the answer unknowable.
"""

from __future__ import annotations

from ramplint.dom import RAW_TEXT_ELEMENTS, Node
from ramplint.template import PLACEHOLDERS

NAMING_ATTRIBUTES = ("aria-label", "aria-labelledby", "title")


def has_naming_attribute(node: Node) -> bool:
    return any(node.has_value(attr) for attr in NAMING_ATTRIBUTES)


def _content_has_name(node: Node) -> bool:
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                return True
            continue
        if child.aria_hidden or child.tag in RAW_TEXT_ELEMENTS:
            continue
        if child.dynamic_attrs:
            return True
        if child.tag in ("img", "area") or (child.tag == "input" and child.get("type") == "image"):
            if child.has_value("alt") or has_naming_attribute(child):
                return True
            continue
        if child.tag == "svg":
            if has_naming_attribute(child) or any(t.text().strip() for t in child.iter("title")):
                return True
            continue
        if child.role == "img" and has_naming_attribute(child):
            return True
        if child.has_value("aria-label") or child.has_value("aria-labelledby"):
            return True
        if _content_has_name(child):
            return True
    return False


def has_accessible_name(node: Node) -> bool:
    """True if the element exposes (or may expose at runtime) a name."""
    if node.dynamic_attrs or has_naming_attribute(node):
        return True
    return _content_has_name(node)


def static_text(node: Node, skip: Node | None = None) -> str | None:
    """The text in ``node`` (without ``skip``); None if any of it is built at runtime."""
    parts: list[str] = []

    def walk(element: Node) -> bool:
        for child in element.children:
            if isinstance(child, str):
                if any(p in child for p in PLACEHOLDERS):
                    return False
                parts.append(child)
            elif (
                child is not skip
                and child.tag not in RAW_TEXT_ELEMENTS
                and (child.dynamic_attrs or not walk(child))
            ):
                return False
        return True

    return " ".join(parts) if walk(node) else None
