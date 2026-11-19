"""``--fix``: rewrite templates where the right fix is not in doubt.

Only attribute values are changed, and only when a rule's suggestion is
unambiguous:

* ``RL202`` th-scope: ``scope="column"`` -> ``scope="col"``.
* ``RL402`` autocomplete-valid: ``autocomplete="emial"`` -> ``"email"``,
  ``"zip"`` -> ``"postal-code"`` (never for passwords: current or new?).
* ``RL503`` no-positive-tabindex: ``tabindex="3"`` -> ``tabindex="0"``.
* ``RL602`` viewport-zoom: ``user-scalable=no`` and ``maximum-scale`` below 2
  are removed from the viewport ``content``.
* ``RL604`` valid-lang: ``lang="ua"`` -> ``lang="uk"``, ``en_US`` -> ``en-US``.

Values built by the template (``{{ }}``, ``{% %}``), elements with generated
attributes and problems silenced with ``ramplint: ignore`` are left alone.
Template positions survive :func:`ramplint.template.prepare`, so edits are
made on the original source at the offsets the parser saw.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ramplint import dom
from ramplint.rules import Rule
from ramplint.rules.document import (
    _DISABLED_SCALING,
    _MIN_MAXIMUM_SCALE,
    _VIEWPORT_SPLIT_RE,
    lang_correction,
)
from ramplint.rules.forms import _autofill_suggestion, autocomplete_error
from ramplint.rules.tables import scope_correction
from ramplint.template import prepare

#: ``attribute -> new value`` for one element.
Edits = dict[str, str]
Fixer = Callable[[dom.Node], Edits]


def _fix_scope(node: dom.Node) -> Edits:
    if node.tag != "th":
        return {}
    match = scope_correction(node.get("scope") or "")
    return {"scope": match} if match else {}


#: Aliases where the intended token is a guess (sign-up or log-in password?).
_AMBIGUOUS_AUTOFILL = frozenset({"password", "pass", "pwd", "address", "street"})


def _fix_autocomplete(node: dom.Node) -> Edits:
    value = node.get("autocomplete") or ""
    if node.tag == "form":
        return {}
    bad = autocomplete_error(value)
    normalized = "".join(char for char in bad or "" if char.isalnum())
    if bad is None or normalized in _AMBIGUOUS_AUTOFILL:
        return {}
    suggestion = _autofill_suggestion(bad)
    if suggestion is None:
        return {}
    tokens = value.split()
    for index, token in enumerate(tokens):
        if token.lower() == bad:
            tokens[index] = suggestion
            fixed = " ".join(tokens)
            # Apply only if it makes the whole value valid.
            return {"autocomplete": fixed} if autocomplete_error(fixed) is None else {}
    return {}  # pragma: no cover - ``bad`` always comes from ``value``


def _fix_tabindex(node: dom.Node) -> Edits:
    return {"tabindex": "0"}


def _fix_viewport(node: dom.Node) -> Edits:
    parts = [part.strip() for part in _VIEWPORT_SPLIT_RE.split(node.get("content") or "")]
    parts = [part for part in parts if part]
    kept = []
    for part in parts:
        key, _, value = part.partition("=")
        key, value = key.strip().lower(), value.strip().lower()
        if key == "user-scalable" and value in _DISABLED_SCALING:
            continue
        if key == "maximum-scale":
            try:
                if 0 < float(value) < _MIN_MAXIMUM_SCALE:
                    continue
            except ValueError:
                pass
        kept.append(part)
    return {} if len(kept) == len(parts) else {"content": ", ".join(kept)}


def _fix_lang(node: dom.Node) -> Edits:
    edits = {}
    for name in ("lang", "xml:lang"):
        value = node.get(name)
        if value is None or node.is_dynamic(name):
            continue
        correction = lang_correction(value)
        if correction is not None:
            edits[name] = correction
    return edits


FIXERS: dict[str, Fixer] = {
    "RL202": _fix_scope,
    "RL402": _fix_autocomplete,
    "RL503": _fix_tabindex,
    "RL602": _fix_viewport,
    "RL604": _fix_lang,
}

#: One attribute in a start tag: name, then an optional quoted or bare value.
_ATTR_RE = re.compile(
    r"""(?P<name>[^\s"'=<>/`]+)(?:\s*=\s*(?P<value>"[^"]*"|'[^']*'|[^\s"'=<>`]+))?"""
)
_TAG_RE = re.compile(r"""<[A-Za-z][^\s/>]*(?:"[^"]*"|'[^']*'|[^'">])*>""")


@dataclass(frozen=True)
class Fix:
    line: int
    col: int
    code: str
    #: ``(start, end, replacement)`` in the source.
    start: int
    end: int
    text: str


def _value_span(html: str, offset: int, attribute: str) -> tuple[int, int, str] | None:
    """``(start, end, quote)`` of ``attribute``'s value in the start tag at ``offset``."""
    tag = _TAG_RE.match(html, offset)
    if tag is None:  # pragma: no cover - the parser saw a start tag here
        return None
    position = offset + 1 + len(re.match(r"[^\s/>]*", html[offset + 1 :]).group(0))
    for match in _ATTR_RE.finditer(html, position, tag.end() - 1):
        if match.group("name").lower() != attribute:
            continue
        value = match.group("value")
        if value is None:  # pragma: no cover - fixers only change values that exist
            return None
        start, end = match.span("value")
        if value[0] in "\"'":
            return start + 1, end - 1, value[0]
        return start, end, ""
    return None  # pragma: no cover - the fixer read the attribute from this tag


def find_fixes(source: str, rules: Iterable[Rule]) -> list[Fix]:
    """The fixes for the problems ``rules`` find in ``source``."""
    prepared = prepare(source)
    root = dom.parse(prepared.html, branch_of=prepared.branches.at, source=source)
    starts = [0, *(i + 1 for i, char in enumerate(source) if char == "\n")]
    fixes: dict[tuple[int, str], Fix] = {}
    for rule in rules:
        fixer = FIXERS.get(rule.code)
        if fixer is None:
            continue
        for node, _message in rule.check(root):
            if node.dynamic_attrs or prepared.suppressions.is_suppressed(
                node.line, rule.code, rule.name
            ):
                continue
            offset = starts[node.line - 1] + node.col - 1
            for attribute, value in fixer(node).items():
                span = (
                    None
                    if node.is_dynamic(attribute)
                    else _value_span(prepared.html, offset, attribute)
                )
                if span is None or (span[2] and span[2] in value):  # pragma: no cover
                    continue  # defensive: rules skip values built by the template
                start, end, quote = span
                text = value if quote else f'"{value}"'
                fixes[(start, attribute)] = Fix(node.line, node.col, rule.code, start, end, text)
    return sorted(fixes.values(), key=lambda f: f.start)


def apply_fixes(source: str, fixes: Iterable[Fix]) -> str:
    """``source`` with ``fixes`` applied (overlapping ones are skipped)."""
    pieces: list[str] = []
    position = 0
    for fix in sorted(fixes, key=lambda f: f.start):
        if fix.start < position:
            continue
        pieces.append(source[position : fix.start])
        pieces.append(fix.text)
        position = fix.end
    pieces.append(source[position:])
    return "".join(pieces)


def fix_source(source: str, rules: Iterable[Rule]) -> tuple[str, list[Fix]]:
    """Fix ``source``; returns the new source and the fixes applied."""
    fixes = find_fixes(source, rules)
    return apply_fixes(source, fixes), fixes
