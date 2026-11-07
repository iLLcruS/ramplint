from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ramplint.dom import Node

if TYPE_CHECKING:
    from ramplint.browser.snapshot import PageSnapshot

#: A check yields ``(node, message)`` pairs for every problem it finds.
Check = Callable[[Node], Iterator[tuple[Node, str]]]


#: A check of a Python module (``forms.py``): yields ``(line, col, message)``.
PythonCheck = Callable[[Any], Iterator[tuple[int, int, str]]]


@dataclass(frozen=True)
class Finding:
    """A problem a rendered-page rule found."""

    #: ``data-rl-node`` of the element (in the state's page when ``state`` is set).
    element: str | None
    message: str
    #: Index into ``PageSnapshot.states`` when the problem is in an opened state.
    state: int | None = None
    #: Needs a person to check it (e.g. text over an image); not a failure.
    manual: bool = False


@dataclass(frozen=True)
class SiteFinding:
    """A problem found by comparing pages; reported on ``page``."""

    page: PageSnapshot
    element: str | None
    message: str
    #: Every page involved.
    pages: tuple[str, ...] = ()


#: A check of one rendered page (browser mode): yields findings.
PageCheck = Callable[["PageSnapshot"], Iterator[Finding]]
#: A check of all pages of a crawl (browser mode).
SiteCheck = Callable[[Sequence["PageSnapshot"]], Iterator[SiteFinding]]


def _no_template_check(root: Node) -> Iterator[tuple[Node, str]]:
    return iter(())


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    summary: str
    wcag: str
    check: Check
    #: Set for rules that check Python code (Django forms) instead of templates.
    python_check: PythonCheck | None = None
    #: Set for rules that need a rendered page (browser mode only).
    page_check: PageCheck | None = None
    #: Also run on the markup of opened menus and dialogs (only what changed).
    on_states: bool = False
    #: Set for rules that compare the pages of a crawl (browser mode only).
    site_check: SiteCheck | None = None

    @property
    def browser_only(self) -> bool:
        return self.page_check is not None or self.site_check is not None

    @property
    def docs_url(self) -> str:
        """The rule's documentation page on GitHub."""
        return f"{DOCS_BASE_URL}/{self.code}.md"


DOCS_BASE_URL = "https://github.com/iLLcruS/ramplint/blob/main/docs/rules"

REGISTRY: dict[str, Rule] = {}


def rule(code: str, name: str, summary: str, wcag: str) -> Callable[[Check], Check]:
    """Register a check function as a rule."""

    def decorator(func: Check) -> Check:
        if code in REGISTRY:  # pragma: no cover - programming error
            raise ValueError(f"Duplicate rule code {code}")
        REGISTRY[code] = Rule(code=code, name=name, summary=summary, wcag=wcag, check=func)
        return func

    return decorator


def python_rule(
    code: str, name: str, summary: str, wcag: str
) -> Callable[[PythonCheck], PythonCheck]:
    """Register a check of Python modules (see :mod:`ramplint.pyforms`)."""

    def decorator(func: PythonCheck) -> PythonCheck:
        if code in REGISTRY:  # pragma: no cover - programming error
            raise ValueError(f"Duplicate rule code {code}")
        REGISTRY[code] = Rule(
            code=code,
            name=name,
            summary=summary,
            wcag=wcag,
            check=_no_template_check,
            python_check=func,
        )
        return func

    return decorator


def _register(rule_: Rule) -> None:
    if rule_.code in REGISTRY:  # pragma: no cover - programming error
        raise ValueError(f"Duplicate rule code {rule_.code}")
    REGISTRY[rule_.code] = rule_


def page_rule(
    code: str, name: str, summary: str, wcag: str, *, on_states: bool = False
) -> Callable[[PageCheck], PageCheck]:
    """Register a check of rendered pages (see :mod:`ramplint.rules.rendered`)."""

    def decorator(func: PageCheck) -> PageCheck:
        _register(
            Rule(
                code=code,
                name=name,
                summary=summary,
                wcag=wcag,
                check=_no_template_check,
                page_check=func,
                on_states=on_states,
            )
        )
        return func

    return decorator


def site_rule(code: str, name: str, summary: str, wcag: str) -> Callable[[SiteCheck], SiteCheck]:
    """Register a check that compares the pages of a crawl (see :mod:`ramplint.rules.site`)."""

    def decorator(func: SiteCheck) -> SiteCheck:
        _register(
            Rule(
                code=code,
                name=name,
                summary=summary,
                wcag=wcag,
                check=_no_template_check,
                site_check=func,
            )
        )
        return func

    return decorator
