from __future__ import annotations

import re
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


_TABINDEX_RE = re.compile(r"^\s*\+?(\d+)\s*$")


@rule(
    code="RL503",
    name="no-positive-tabindex",
    summary="tabindex must not be greater than 0.",
    wcag="2.4.3 Focus Order (A)",
)
def no_positive_tabindex(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter():
        value = node.get("tabindex")
        if value is None or node.is_dynamic("tabindex"):
            continue
        match = _TABINDEX_RE.match(value)
        if not match or int(match.group(1)) == 0:
            continue
        yield (
            node,
            f'tabindex="{value.strip()}" overrides the natural focus order; use '
            'tabindex="0" to make the element focusable, or reorder the markup',
        )


_JAVASCRIPT_URL_RE = re.compile(r"^\s*javascript\s*:", re.IGNORECASE)


@rule(
    code="RL504",
    name="anchor-is-valid",
    summary="Links must point somewhere; use <button> for actions.",
    wcag="2.1.1 Keyboard (A), 4.1.2 Name, Role, Value (A)",
)
def anchor_is_valid(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("a"):
        if node.dynamic_attrs:
            continue
        href = node.get("href")

        if href is None:
            # <a name="..."> / <a id="..."> placeholders are fine; an <a> that
            # reacts to clicks but has no href is not reachable by keyboard.
            if any(attr.startswith("on") for attr in node.attrs):
                yield (
                    node,
                    "<a> without href is not keyboard accessible; use a <button> for actions",
                )
            continue

        if node.is_dynamic("href"):
            continue
        if href.strip() == "#" or _JAVASCRIPT_URL_RE.match(href):
            yield (
                node,
                f'<a href="{href.strip()}"> is used as a button; use a <button> for '
                "actions, or link to a real URL or #fragment",
            )
