"""WAI-ARIA rules (RL7xx)."""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules import aria_data as data
from ramplint.rules.base import rule
from ramplint.template import MARKUP

_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _suggest(value: str, choices: frozenset[str]) -> str:
    match = difflib.get_close_matches(value, choices, n=1, cutoff=0.6)
    return f'; did you mean "{match[0]}"?' if match else ""


def effective_role(node: Node) -> str | None:
    """The role a browser uses: the first valid, non-abstract token."""
    if node.is_dynamic("role"):
        return None
    for token in node.role.split():
        if token in data.ROLES:
            return token
    return None


# --------------------------------------------------------------------------
# RL701 aria-role
# --------------------------------------------------------------------------


@rule(
    code="RL701",
    name="aria-role",
    summary="role values must be valid, non-abstract WAI-ARIA roles.",
    wcag="4.1.2 Name, Role, Value (A)",
)
def aria_role(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter():
        value = node.get("role")
        if value is None or not value.strip() or node.is_dynamic("role"):
            continue
        tokens = value.lower().split()
        for token in tokens:
            if token in data.ROLES:
                break  # browsers use the first role they recognise
            if token in data.ABSTRACT_ROLES:
                yield (
                    node,
                    f'role="{token}" is an abstract role and must not be used in markup',
                )
                break
        else:
            first = tokens[0]
            yield (
                node,
                f'role="{value.strip()}" is not a WAI-ARIA role{_suggest(first, data.ROLES)}',
            )


# --------------------------------------------------------------------------
# RL702 aria-valid-attr
# --------------------------------------------------------------------------


@rule(
    code="RL702",
    name="aria-valid-attr",
    summary="aria-* attributes must exist in WAI-ARIA.",
    wcag="4.1.2 Name, Role, Value (A)",
)
def aria_valid_attr(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter():
        for name in node.attrs:
            if name.startswith("aria-") and name not in data.ATTRIBUTES:
                yield (
                    node,
                    f"{name} is not a WAI-ARIA attribute and is ignored"
                    f"{_suggest(name, data.ATTRIBUTES)}",
                )


# --------------------------------------------------------------------------
# RL703 aria-valid-attr-value
# --------------------------------------------------------------------------


def _static_ids(root: Node) -> set[str] | None:
    """All ids in the template, or None if some may be rendered elsewhere."""
    if MARKUP in root.text():
        return None
    ids: set[str] = set()
    for node in root.iter():
        if node.dynamic_attrs or node.is_dynamic("id"):
            return None
        element_id = (node.get("id") or "").strip()
        if element_id:
            ids.add(element_id)
    return ids


def _value_problem(name: str, value: str) -> str | None:
    stripped = value.strip()
    lowered = stripped.lower()
    if name in data.TOKEN_VALUES:
        allowed = data.TOKEN_VALUES[name]
        if lowered not in allowed:
            options = ", ".join(sorted(allowed))
            return f'{name}="{stripped}" is not valid; use one of: {options}'
    elif name in data.TOKEN_LIST_VALUES:
        allowed = data.TOKEN_LIST_VALUES[name]
        bad = [token for token in lowered.split() if token not in allowed]
        if bad or not lowered:
            options = ", ".join(sorted(allowed))
            return f'{name}="{stripped}" is not valid; use tokens from: {options}'
    elif name in data.INTEGER_VALUES:
        minimum = data.INTEGER_VALUES[name]
        if not _INTEGER_RE.match(stripped) or int(stripped) < minimum:
            return f'{name}="{stripped}" must be an integer of at least {minimum}'
    elif name in data.NUMBER_VALUES:
        if not _NUMBER_RE.match(stripped):
            return f'{name}="{stripped}" must be a number'
    elif name in data.ID_REFERENCE_LISTS and not stripped:
        return f"{name} is empty; reference the id of an element"
    return None


@rule(
    code="RL703",
    name="aria-valid-attr-value",
    summary="ARIA attribute values must match the attribute's type.",
    wcag="4.1.2 Name, Role, Value (A)",
)
def aria_valid_attr_value(root: Node) -> Iterator[tuple[Node, str]]:
    known_ids = _static_ids(root)
    for node in root.iter():
        for name, value in node.attrs.items():
            if name not in data.ATTRIBUTES or node.is_dynamic(name):
                continue
            problem = _value_problem(name, value)
            if problem:
                yield node, problem
                continue
            if known_ids is not None and name in data.ID_REFERENCES:
                missing = [ref for ref in value.split() if ref not in known_ids]
                if missing:
                    refs = ", ".join(f'"{ref}"' for ref in missing)
                    yield node, f"{name} references missing id {refs}"


# --------------------------------------------------------------------------
# RL704 aria-required-attr
# --------------------------------------------------------------------------

_NATIVE_STATE = {
    # role -> (tag, input types) that provide the state natively
    "checkbox": ("input", {"checkbox"}),
    "switch": ("input", {"checkbox"}),
    "radio": ("input", {"radio"}),
    "menuitemcheckbox": ("input", {"checkbox"}),
    "menuitemradio": ("input", {"radio"}),
    "slider": ("input", {"range"}),
}


def _has_native_state(node: Node, role: str) -> bool:
    if role == "heading" and node.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return True
    if role == "combobox" and node.tag == "select":
        return True
    native = _NATIVE_STATE.get(role)
    if native is None:
        return False
    tag, types = native
    return node.tag == tag and (node.get("type") or "").strip().lower() in types


@rule(
    code="RL704",
    name="aria-required-attr",
    summary="Elements with a role must have the ARIA attributes that role requires.",
    wcag="4.1.2 Name, Role, Value (A)",
)
def aria_required_attr(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter():
        if node.dynamic_attrs:
            continue
        role = effective_role(node)
        required = data.REQUIRED_ATTRIBUTES.get(role or "")
        if not required or _has_native_state(node, role or ""):
            continue
        missing = [attr for attr in required if attr not in node.attrs]
        if missing:
            yield (
                node,
                f'role="{role}" requires {", ".join(missing)}; screen readers '
                "need it to announce the element correctly",
            )


# --------------------------------------------------------------------------
# RL705 aria-hidden-focus
# --------------------------------------------------------------------------

_FOCUSABLE_TAGS = frozenset({"button", "select", "textarea", "iframe", "summary"})


def _is_focusable(node: Node) -> bool | None:
    """True/False, or None when it cannot be known statically."""
    if node.dynamic_attrs or node.is_dynamic("tabindex"):
        return None
    tabindex = node.get("tabindex")
    if tabindex is not None:
        try:
            return int(tabindex.strip()) >= 0
        except ValueError:
            pass
    if "disabled" in node.attrs:
        return False
    if node.tag == "a" or node.tag == "area":
        return node.get("href") is not None
    if node.tag == "input":
        return (node.get("type") or "").strip().lower() != "hidden"
    if node.tag in _FOCUSABLE_TAGS:
        return True
    return (node.get("contenteditable") or "").strip().lower() in ("", "true") and (
        "contenteditable" in node.attrs
    )


def _describe(node: Node) -> str:
    return f"<{node.tag}>"


@rule(
    code="RL705",
    name="aria-hidden-focus",
    summary='Content with aria-hidden="true" must not be focusable.',
    wcag="4.1.2 Name, Role, Value (A)",
)
def aria_hidden_focus(root: Node) -> Iterator[tuple[Node, str]]:
    reported: set[int] = set()
    for hidden in root.iter():
        if not hidden.aria_hidden or hidden.is_dynamic("aria-hidden"):
            continue
        candidates = [hidden, *(n for n in hidden.iter() if n.tag != "template")]
        for node in candidates:
            if id(node) in reported or _is_focusable(node) is not True:
                continue
            if any(a.tag == "template" for a in node.ancestors()):
                continue
            reported.add(id(node))
            if node is hidden:
                message = (
                    f'{_describe(node)} has aria-hidden="true" but can still receive '
                    'keyboard focus; remove aria-hidden or add tabindex="-1"'
                )
            else:
                message = (
                    f'Focusable {_describe(node)} inside aria-hidden="true" (line '
                    f"{hidden.line}); screen reader users can tab to content they "
                    'cannot hear. Add tabindex="-1" or remove aria-hidden'
                )
            yield node, message
