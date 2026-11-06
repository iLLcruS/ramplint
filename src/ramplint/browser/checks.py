"""Run the template rules (RL1xx-RL7xx) on rendered pages.

The rendered page has no ``{{ }}`` and no ``{% %}``: what a rule sees is what the
browser got, including markup added by JavaScript. Two things the browser knows
better than the markup are used to avoid false positives:

* elements that are not rendered (``display: none``, ``visibility: hidden``)
  are skipped by rules about content, the way assistive technology skips them;
* when Chromium computes a non-empty accessible name for an element, rules that
  report a missing name trust the browser.
"""

from __future__ import annotations

from collections.abc import Iterable

from ramplint import dom
from ramplint.browser.snapshot import PageSnapshot
from ramplint.linter import Violation
from ramplint.rules import Rule
from ramplint.template import prepare

#: Rules about template code or ``forms.py`` that have no meaning in a rendered page.
TEMPLATE_ONLY_RULES = frozenset({"RL404", "RL405", "RL406"})

#: Rules that apply to markup whether or not it is rendered.
# fmt: off
VISIBILITY_INDEPENDENT_RULES = frozenset(
    {
        "RL303", "RL306", "RL503", "RL506",
        "RL601", "RL602", "RL603", "RL604", "RL605", "RL606",
        "RL701", "RL702", "RL703", "RL704",
    }
)
# fmt: on

#: Rules that report a missing accessible name.
NAME_RULES = frozenset({"RL102", "RL104", "RL302", "RL501", "RL502"})

NODE_ATTRIBUTE = "data-rl-node"


def browser_rules(rules: Iterable[Rule]) -> list[Rule]:
    """The rules that make sense for rendered pages."""
    return [rule for rule in rules if rule.code not in TEMPLATE_ONLY_RULES]


def check_snapshot(snapshot: PageSnapshot, rules: Iterable[Rule]) -> list[Violation]:
    """Problems in one rendered page. Pages that did not load have none."""
    if not snapshot.is_html or not snapshot.html:
        return []
    root = dom.parse(snapshot.html)
    # ``<!-- ramplint: ignore ... -->`` comments survive rendering.
    suppressions = prepare(snapshot.html).suppressions
    found: dict[tuple[str, int, int, str], Violation] = {}
    for rule in browser_rules(rules):
        for node, message in rule.check(root):
            if suppressions.is_suppressed(node.line, rule.code, rule.name):
                continue
            element = snapshot.element(node.get(NODE_ATTRIBUTE))
            if element is not None:
                if not element.visible and rule.code not in VISIBILITY_INDEPENDENT_RULES:
                    continue
                if rule.code in NAME_RULES and (element.name or "").strip():
                    continue
            selector = element.selector if element is not None else node.tag
            found[(rule.code, node.line, node.col, message)] = Violation(
                path=snapshot.url,
                line=node.line,
                col=node.col,
                code=rule.code,
                name=rule.name,
                message=message,
                url=snapshot.url,
                selector=selector,
                viewport=snapshot.viewport,
                bbox=element.box if element is not None else None,
            )
    return sorted(found.values())


def merge_viewports(violations: Iterable[Violation]) -> list[Violation]:
    """One problem per URL, rule, element and message, listing every viewport."""
    merged: dict[tuple[str, str, str | None, str], Violation] = {}
    viewports: dict[tuple[str, str, str | None, str], list[str]] = {}
    for v in violations:
        key = (v.path, v.code, v.selector, v.message)
        if key not in merged:
            merged[key] = v
            viewports[key] = []
        if v.viewport and v.viewport not in viewports[key]:
            viewports[key].append(v.viewport)
    result = []
    for key, v in merged.items():
        names = ",".join(viewports[key]) or None
        result.append(
            Violation(
                path=v.path,
                line=v.line,
                col=v.col,
                code=v.code,
                name=v.name,
                message=v.message,
                url=v.url,
                selector=v.selector,
                viewport=names,
                bbox=v.bbox,
            )
        )
    return sorted(result, key=lambda v: (v.path, v.line, v.col, v.code, v.selector or ""))
