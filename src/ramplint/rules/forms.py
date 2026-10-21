from __future__ import annotations

import difflib
from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.rules.names import has_naming_attribute
from ramplint.template import MARKUP, PLACEHOLDERS

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


# Autofill tokens from the HTML Living Standard
# https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#autofill
# fmt: off
AUTOFILL_FIELDS = frozenset({
    "name", "honorific-prefix", "given-name", "additional-name", "family-name",
    "honorific-suffix", "nickname", "username", "new-password", "current-password",
    "one-time-code", "organization-title", "organization", "street-address",
    "address-line1", "address-line2", "address-line3", "address-level4",
    "address-level3", "address-level2", "address-level1", "country", "country-name",
    "postal-code", "cc-name", "cc-given-name", "cc-additional-name", "cc-family-name",
    "cc-number", "cc-exp", "cc-exp-month", "cc-exp-year", "cc-csc", "cc-type",
    "transaction-currency", "transaction-amount", "language", "bday", "bday-day",
    "bday-month", "bday-year", "sex", "url", "photo",
})
AUTOFILL_CONTACT_FIELDS = frozenset({
    "tel", "tel-country-code", "tel-national", "tel-area-code", "tel-local",
    "tel-local-prefix", "tel-local-suffix", "tel-extension", "email", "impp",
})
# fmt: on
_ADDRESS_TYPES = frozenset({"shipping", "billing"})
_CONTACT_TYPES = frozenset({"home", "work", "mobile", "fax", "pager"})
_ALL_KNOWN = (
    AUTOFILL_FIELDS
    | AUTOFILL_CONTACT_FIELDS
    | _ADDRESS_TYPES
    | _CONTACT_TYPES
    | {"on", "off", "webauthn"}
)


def autocomplete_error(value: str) -> str | None:
    """Return the first invalid token of an autocomplete value, or None if valid.

    Grammar: [section-*] [shipping|billing] [home|work|mobile|fax|pager] field
    [webauthn], or a lone "on" / "off".
    """
    tokens = value.lower().split()
    if not tokens or tokens in (["on"], ["off"]):
        return None
    i = 0
    if tokens[i].startswith("section-") and len(tokens[i]) > len("section-"):
        i += 1
    if i < len(tokens) and tokens[i] in _ADDRESS_TYPES:
        i += 1
    contact = i < len(tokens) and tokens[i] in _CONTACT_TYPES
    if contact:
        i += 1
    if i >= len(tokens):
        return tokens[-1]
    field = tokens[i]
    allowed = AUTOFILL_CONTACT_FIELDS if contact else AUTOFILL_FIELDS | AUTOFILL_CONTACT_FIELDS
    if field not in allowed:
        return field
    i += 1
    if i < len(tokens) and tokens[i] == "webauthn":
        i += 1
    return tokens[i] if i < len(tokens) else None


@rule(
    code="RL402",
    name="autocomplete-valid",
    summary="autocomplete must use valid autofill tokens.",
    wcag="1.3.5 Identify Input Purpose (AA)",
)
def autocomplete_valid(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("input", "select", "textarea", "form"):
        value = node.get("autocomplete")
        if value is None or not value.strip() or node.is_dynamic("autocomplete"):
            continue
        if node.tag == "form":
            if value.strip().lower() in ("on", "off"):
                continue
            yield node, f'<form autocomplete="{value.strip()}"> only accepts "on" or "off"'
            continue

        bad = autocomplete_error(value)
        if bad is None:
            continue
        suggestion = difflib.get_close_matches(bad, _ALL_KNOWN, n=1, cutoff=0.6)
        hint = f'did you mean "{suggestion[0]}"?' if suggestion else 'use "off" to disable autofill'
        yield (
            node,
            f'autocomplete="{value.strip()}" is not valid: unknown or misplaced token '
            f'"{bad}"; {hint}',
        )


_LABELABLE = frozenset({"input", "select", "textarea", "button", "meter", "output", "progress"})


def _template_ids(root: Node) -> dict[str, Node] | None:
    """Every id in the template, or None if some may be rendered elsewhere."""
    if MARKUP in root.text():
        # {% include %}, {{ form.email }}, {% block %} of a base template ...
        # A {% block %} of a child template renders its own content, which
        # is right here, so it does not hide the target.
        return None
    ids: dict[str, Node] = {}
    for node in root.iter():
        if node.dynamic_attrs or node.is_dynamic("id"):
            return None
        element_id = (node.get("id") or "").strip()
        if element_id:
            ids.setdefault(element_id, node)
    return ids


def _for_hint(root: Node, target: str, ids: dict[str, Node]) -> str:
    for node in root.iter(*_LABELABLE):
        if (node.get("name") or "").strip() == target and not node.has_value("id"):
            return f'; add id="{target}" to the <{node.tag} name="{target}">'
    match = difflib.get_close_matches(target, ids, n=1, cutoff=0.7)
    return f'; did you mean "{match[0]}"?' if match else ""


@rule(
    code="RL403",
    name="label-for-target",
    summary="<label for> must point to an element id in the template.",
    wcag="1.3.1 Info and Relationships (A), 4.1.2 Name, Role, Value (A)",
)
def label_for_target(root: Node) -> Iterator[tuple[Node, str]]:
    ids = _template_ids(root)
    if ids is None:
        return
    for label in root.iter("label"):
        target = label.get("for")
        if target is None or label.is_dynamic("for") or label.inert:
            continue
        target = target.strip()
        if not target:
            yield label, '<label for=""> is empty; set it to the id of the field it labels'
        elif target not in ids:
            yield (
                label,
                f'<label for="{target}"> points to no element with id="{target}", so the '
                f"field has no name and clicking the label does nothing"
                f"{_for_hint(root, target, ids)}",
            )
