"""Run the rules on rendered pages.

The template rules (RL1xx-RL7xx) see the rendered HTML: no ``{{ }}`` and no
``{% %}``, but everything JavaScript added. Two things the browser knows better
than the markup are used to avoid false positives:

* elements that are not rendered (``display: none``, ``visibility: hidden``)
  are skipped by rules about content, the way assistive technology skips them;
* when Chromium computes a non-empty accessible name for an element, rules that
  report a missing name trust the browser.

Rendered-page rules (RL8xx) read the snapshot itself, and both kinds also run
on the markup of opened menus and dialogs - only on what the click changed.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field, replace

from ramplint import dom
from ramplint.browser.snapshot import NODE_ATTRIBUTE, PageSnapshot
from ramplint.browser.urls import url_pattern
from ramplint.linter import Violation
from ramplint.rules import Rule
from ramplint.rules.base import Finding
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


@dataclass(frozen=True)
class ManualCheck:
    """Something a rule could not decide; a person has to look at it."""

    url: str
    selector: str | None
    code: str
    message: str


@dataclass
class PageResult:
    violations: list[Violation] = field(default_factory=list)
    manual: list[ManualCheck] = field(default_factory=list)


def browser_rules(rules: Iterable[Rule]) -> list[Rule]:
    """Template rules that make sense for rendered markup."""
    return [
        rule for rule in rules if rule.code not in TEMPLATE_ONLY_RULES and not rule.browser_only
    ]


def check_page(snapshot: PageSnapshot, rules: Iterable[Rule]) -> PageResult:
    """Every problem in one captured page and the menus and dialogs opened on it."""
    rules = list(rules)
    result = PageResult(check_snapshot(snapshot, rules))
    page_rules = [rule for rule in rules if rule.page_check is not None]
    for rule in page_rules:
        assert rule.page_check is not None
        for finding in rule.page_check(snapshot):
            _add(result, rule, snapshot, finding)
    for index, state in enumerate(snapshot.states):
        changed = set(state.changed)
        if not changed:
            continue
        for v in check_snapshot(state.page, rules, only=changed):
            result.violations.append(replace(v, state=state.description))
        for rule in page_rules:
            if not rule.on_states:
                continue
            assert rule.page_check is not None
            for finding in rule.page_check(state.page):
                if finding.element in changed:
                    _add(result, rule, snapshot, replace(finding, state=index))
    return result


def _add(result: PageResult, rule: Rule, snapshot: PageSnapshot, finding: Finding) -> None:
    page = snapshot if finding.state is None else snapshot.states[finding.state].page
    element = page.element(finding.element)
    selector = element.selector if element is not None else None
    if finding.manual:
        result.manual.append(ManualCheck(snapshot.url, selector, rule.code, finding.message))
        return
    node = page.tree.nodes.get(finding.element or "")
    if node is not None and page.suppressions.is_suppressed(node.line, rule.code, rule.name):
        return
    result.violations.append(
        Violation(
            path=snapshot.url,
            line=node.line if node else 1,
            col=node.col if node else 1,
            code=rule.code,
            name=rule.name,
            message=finding.message,
            url=snapshot.url,
            selector=selector,
            viewport=snapshot.viewport,
            bbox=element.box if element is not None else None,
            state=snapshot.states[finding.state].description if finding.state is not None else None,
            template=element.source if element is not None else None,
        )
    )


def check_site(snapshots: Sequence[PageSnapshot], rules: Iterable[Rule]) -> list[Violation]:
    """Problems found by comparing pages (RL9xx); each lists every page involved."""
    violations = []
    for rule in rules:
        if rule.site_check is None:
            continue
        for finding in rule.site_check(snapshots):
            page = finding.page
            element = page.element(finding.element)
            node = page.tree.nodes.get(finding.element or "")
            if node is not None and page.suppressions.is_suppressed(
                node.line, rule.code, rule.name
            ):
                continue
            violations.append(
                Violation(
                    path=page.url,
                    line=node.line if node else 1,
                    col=node.col if node else 1,
                    code=rule.code,
                    name=rule.name,
                    message=finding.message,
                    url=page.url,
                    selector=element.selector if element is not None else None,
                    viewport=page.viewport,
                    bbox=element.box if element is not None else None,
                    pages=finding.pages or (page.url,),
                    template=element.source if element is not None else None,
                )
            )
    return violations


def check_snapshot(
    snapshot: PageSnapshot, rules: Iterable[Rule], only: Collection[str] | None = None
) -> list[Violation]:
    """Template rules on one rendered page. Pages that did not load have none.

    ``only`` limits the problems to these elements (``data-rl-node`` values) and
    the elements inside them.
    """
    if not snapshot.is_html or not snapshot.html:
        return []
    root = snapshot.tree.root
    suppressions = snapshot.suppressions
    found: dict[tuple[str, int, int, str], Violation] = {}
    for rule in browser_rules(rules):
        for node, message in rule.check(root):
            if suppressions.is_suppressed(node.line, rule.code, rule.name):
                continue
            node_id = node.get(NODE_ATTRIBUTE)
            if only is not None and not _within(node, only):
                continue
            element = snapshot.element(node_id)
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
                template=element.source if element is not None else None,
            )
    return sorted(found.values())


def _within(node: dom.Node, ids: Collection[str]) -> bool:
    current: dom.Node | None = node
    while current is not None:
        if current.get(NODE_ATTRIBUTE) in ids:
            return True
        current = current.parent
    return False


def css_path(node: dom.Node) -> str:
    """A CSS selector for an element of a parsed page (``#id`` or a tag path)."""
    steps: list[str] = []
    current: dom.Node | None = node
    while current is not None and current.tag not in ("#document", "html", "body"):
        if current.get("id"):
            steps.append(f"#{current.attrs['id']}")
            break
        parent = current.parent
        siblings = [
            child for child in (parent.children if parent else []) if isinstance(child, dom.Node)
        ]
        same = [child for child in siblings if child.tag == current.tag]
        if len(same) > 1:
            steps.append(f"{current.tag}:nth-of-type({same.index(current) + 1})")
        else:
            steps.append(current.tag)
        current = parent
    return " > ".join(reversed(steps)) or node.tag


def check_fragment(url: str, html: str, rules: Iterable[Rule]) -> list[Violation]:
    """Problems in an HTML fragment (``hx-get``, ``fetch``) loaded into a page.

    A fragment is linted like a partial template: rules about whole documents
    (``html-lang``, ``document-title``) do not apply to it.
    """
    root = dom.parse(html)
    suppressions = prepare(html).suppressions
    found: dict[tuple[str, int, int, str], Violation] = {}
    for rule in browser_rules(rules):
        for node, message in rule.check(root):
            if suppressions.is_suppressed(node.line, rule.code, rule.name):
                continue
            found[(rule.code, node.line, node.col, message)] = Violation(
                path=url,
                line=node.line,
                col=node.col,
                code=rule.code,
                name=rule.name,
                message=message,
                url=url,
                selector=css_path(node),
                viewport="fragment",
            )
    return sorted(found.values())


def merge_findings(violations: Iterable[Violation]) -> list[Violation]:
    """One problem per rule, element and message on pages of the same URL pattern.

    ``/products/1/`` and ``/products/2/`` come from the same template, so the
    same problem on both is reported once; it lists every page in ``pages``
    and every viewport in ``viewport``. ``path`` and ``url`` are the first page.
    With a template source map, problems at the same template location merge
    across URL patterns too.
    """
    groups: dict[tuple[object, ...], list[Violation]] = {}
    for v in violations:
        where = v.template or url_pattern(v.url or v.path)
        key = (where, v.code, v.selector if not v.template else None, v.message, v.state)
        groups.setdefault(key, []).append(v)
    result = []
    for items in groups.values():
        pages = tuple(sorted({page for v in items for page in v.locations}))
        first = min(items, key=lambda v: (v.path != pages[0], v.path, v.line, v.col))
        result.append(
            replace(
                first,
                viewport=_union(v.viewport for v in items),
                role=_union(v.role for v in items),
                pages=pages,
            )
        )
    return sorted(result, key=lambda v: (v.path, v.line, v.col, v.code, v.selector or ""))


def _union(values: Iterable[str | None]) -> str | None:
    """``desktop,mobile`` from ``desktop``, ``mobile,desktop``... in first-seen order."""
    names: list[str] = []
    for value in values:
        for name in (value or "").split(","):
            if name and name not in names:
                names.append(name)
    return ",".join(names) or None


def merge_static(browser: list[Violation], static: Iterable[Violation]) -> list[Violation]:
    """Template-linter findings next to browser findings, each problem once.

    A static finding at the template location of a browser finding (same rule)
    is the same problem: the browser finding stays, marked as confirmed.
    """
    by_location = {}
    for v in browser:
        location = v.template_location
        if location is not None:
            by_location[(*location, v.code)] = v
    confirmed: set[int] = set()
    kept = []
    for v in static:
        match = by_location.get((v.path, v.line, v.col, v.code))
        if match is None:
            kept.append(v)
        else:
            confirmed.add(id(match))
    merged = [replace(v, confirmed=True) if id(v) in confirmed else v for v in browser]
    return [*merged, *sorted(kept)]
