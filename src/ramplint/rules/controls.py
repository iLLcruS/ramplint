from __future__ import annotations

import re
from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.aria import effective_role
from ramplint.rules.base import rule
from ramplint.rules.ids import rendered_elements
from ramplint.rules.names import has_accessible_name, has_naming_attribute
from ramplint.template import mutually_exclusive


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


_INTERACTIVE_TAGS = frozenset({"a", "button", "select", "textarea", "input", "details", "summary"})
_INTERACTIVE_ROLES = frozenset(
    {
        "button", "checkbox", "combobox", "link", "listbox", "menuitem",
        "menuitemcheckbox", "menuitemradio", "option", "radio", "searchbox",
        "slider", "spinbutton", "switch", "tab", "textbox", "treeitem",
    }
)  # fmt: skip


def _is_interactive_container(node: Node) -> bool:
    return node.tag == "button" or (node.tag == "a" and node.get("href") is not None)


def _is_interactive_element(node: Node) -> bool:
    if node.tag == "a":
        return node.get("href") is not None
    if node.tag == "input":
        return (node.get("type") or "").strip().lower() != "hidden"
    if node.tag == "summary":
        # A <summary> inside <details> is reported as part of the <details>.
        return not any(ancestor.tag == "details" for ancestor in node.ancestors())
    return True


def _interactive_kind(node: Node) -> str | None:
    """How ``node`` is interactive, or None if it is not (or cannot be known)."""
    if node.dynamic_attrs:
        return None
    if node.tag in _INTERACTIVE_TAGS and _is_interactive_element(node):
        if node.tag == "input":
            return f'<input type="{(node.get("type") or "text").strip().lower()}">'
        return f"<{node.tag}>"
    role = effective_role(node)
    if role in _INTERACTIVE_ROLES:
        return f'<{node.tag} role="{role}">'
    tabindex = node.get("tabindex")
    if tabindex is not None and not node.is_dynamic("tabindex"):
        match = _TABINDEX_RE.match(tabindex)
        if match:  # tabindex="0" or more; negative values do not match
            return f'<{node.tag} tabindex="{tabindex.strip()}">'
    return None


@rule(
    code="RL505",
    name="nested-interactive",
    summary="Interactive elements must not contain other interactive elements.",
    wcag="4.1.2 Name, Role, Value (A)",
)
def nested_interactive(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter():
        if node.inert:
            continue
        container = next((a for a in node.ancestors() if _is_interactive_container(a)), None)
        if container is None:
            continue
        kind = _interactive_kind(node)
        if kind is None:
            continue
        outer = "<button>" if container.tag == "button" else "<a href>"
        yield (
            node,
            f"{kind} is nested inside {outer} (line {container.line}); screen readers "
            "and keyboards cannot reach the inner control reliably. Move it outside",
        )


@rule(
    code="RL506",
    name="duplicate-accesskey",
    summary="accesskey values must be unique within a template.",
    wcag="Best practice (related to 2.1.4 Character Key Shortcuts (A))",
)
def duplicate_accesskey(root: Node) -> Iterator[tuple[Node, str]]:
    seen: dict[str, list[Node]] = {}
    for node in rendered_elements(root):
        value = node.get("accesskey")
        if value is None or node.is_dynamic("accesskey") or not value.strip():
            continue
        key = value.strip().lower()
        previous = seen.setdefault(key, [])
        clash = next(
            (other for other in previous if not mutually_exclusive(other.branch, node.branch)),
            None,
        )
        previous.append(node)
        if clash is not None:
            yield (
                node,
                f'accesskey="{value.strip()}" is already used on line {clash.line}; the '
                "shortcut can only activate one of them. Pick a different key",
            )
