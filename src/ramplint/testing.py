"""Accessibility checks in your test suite.

Lint the HTML your views render, with the Django test client and no browser::

    from ramplint.testing import assert_accessible

    def test_product_list(client):
        response = client.get("/products/")
        assert_accessible(response)

or in a ``TestCase``::

    from django.test import TestCase
    from ramplint.testing import AccessibilityTestMixin

    class ProductTests(AccessibilityTestMixin, TestCase):
        def test_list(self):
            self.assertAccessible(self.client.get("/products/"))

The template rules run on the rendered page, so problems that only exist
after rendering (a context variable that is empty, an ``{% if %}`` branch the
template linter cannot pick) are found too. ``select`` and ``ignore`` of
``[tool.ramplint]`` in ``pyproject.toml`` apply; pass ``select=`` /
``ignore=`` to change them for one check. With
:class:`ramplint.django.SourceMapLoader` active (``DEBUG`` on), every problem
also names the template line that produced the element.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any

from ramplint.config import Config, ConfigError, load_config
from ramplint.linter import Violation, lint_source
from ramplint.rules import Rule, select_rules, unknown_selectors
from ramplint.sourcemap import SOURCE_ATTRIBUTE

__all__ = [
    "AccessibilityError",
    "AccessibilityTestMixin",
    "assert_accessible",
    "check_html",
    "check_response",
]

_HTML_TYPES = ("text/html", "application/xhtml+xml")


class AccessibilityError(AssertionError):
    """Raised by :func:`assert_accessible`; ``violations`` lists the problems."""

    def __init__(self, message: str, violations: Sequence[Violation]) -> None:
        super().__init__(message)
        self.violations = list(violations)


@lru_cache(maxsize=1)
def _project_config() -> Config:
    try:
        return load_config()
    except ConfigError:
        return Config()


def _rules(select: Iterable[str] | None, ignore: Iterable[str] | None) -> list[Rule]:
    config = _project_config()
    chosen = list(select) if select is not None else config.select
    skipped = [*config.ignore, *(ignore or [])]
    unknown = unknown_selectors([*chosen, *skipped])
    if unknown:
        raise ValueError(f"unknown rule(s): {', '.join(unknown)}")
    # Rendered HTML: no forms modules, no browser.
    return [
        rule
        for rule in select_rules(chosen, skipped)
        if rule.python_check is None and not rule.browser_only
    ]


class _SourceMap(HTMLParser):
    """``(line, col)`` of each start tag -> its ``data-rl-src`` value."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.locations: dict[tuple[int, int], str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == SOURCE_ATTRIBUTE and value:
                line, offset = self.getpos()
                self.locations[(line, offset + 1)] = value

    handle_startendtag = handle_starttag


def _template_locations(html: str) -> dict[tuple[int, int], str]:
    if SOURCE_ATTRIBUTE not in html:
        return {}
    parser = _SourceMap()
    parser.feed(html)
    parser.close()
    return parser.locations


def check_html(
    html: str,
    *,
    select: Iterable[str] | None = None,
    ignore: Iterable[str] | None = None,
    path: str = "<html>",
) -> list[Violation]:
    """The accessibility problems in rendered ``html``."""
    violations = lint_source(html, path=path, rules=_rules(select, ignore))
    locations = _template_locations(html)
    if not locations:
        return violations
    return [replace(v, template=locations.get((v.line, v.col))) for v in violations]


def _response_path(response: Any) -> str:
    request = getattr(response, "wsgi_request", None) or getattr(response, "asgi_request", None)
    if request is not None and getattr(request, "path", None):
        return str(request.path)
    environ = getattr(response, "request", None)
    if isinstance(environ, dict) and environ.get("PATH_INFO"):
        return str(environ["PATH_INFO"])
    return "<response>"


def _content_type(response: Any) -> str:
    headers = getattr(response, "headers", None)
    value = headers.get("Content-Type") if headers is not None else None
    if value is None and hasattr(response, "get"):
        value = response.get("Content-Type")
    return str(value or "text/html")


def check_response(
    response: Any,
    *,
    select: Iterable[str] | None = None,
    ignore: Iterable[str] | None = None,
) -> list[Violation]:
    """The problems in a Django test client response (``[]`` for JSON, files, ...)."""
    content_type = _content_type(response)
    if content_type.split(";")[0].strip().lower() not in _HTML_TYPES:
        return []
    if getattr(response, "streaming", False):
        raise ValueError(
            "ramplint cannot check a streaming response without consuming it; "
            "pass its HTML to check_html()"
        )
    charset = getattr(response, "charset", None) or "utf-8"
    html = bytes(response.content).decode(charset, errors="replace")
    return check_html(html, select=select, ignore=ignore, path=_response_path(response))


def _describe(violations: Sequence[Violation], where: str) -> str:
    count = len(violations)
    lines = [f"{count} accessibility problem{'s' if count != 1 else ''} in {where}:"]
    for v in violations:
        template = f" ({v.template})" if v.template else ""
        lines.append(f"  {v.line}:{v.col}: {v.code} {v.message} [{v.name}]{template}")
    return "\n".join(lines)


def assert_accessible(
    response_or_html: Any,
    *,
    select: Iterable[str] | None = None,
    ignore: Iterable[str] | None = None,
) -> None:
    """Fail with every problem found in a response or an HTML string."""
    if isinstance(response_or_html, (str, bytes)):
        html = (
            response_or_html.decode("utf-8", errors="replace")
            if isinstance(response_or_html, bytes)
            else response_or_html
        )
        violations = check_html(html, select=select, ignore=ignore)
        where = "the HTML"
    else:
        violations = check_response(response_or_html, select=select, ignore=ignore)
        where = _response_path(response_or_html)
    if violations:
        raise AccessibilityError(_describe(violations, where), violations)


class AccessibilityTestMixin:
    """Adds ``assertAccessible(response)`` to a ``unittest`` / Django ``TestCase``."""

    def assertAccessible(
        self,
        response_or_html: Any,
        *,
        select: Iterable[str] | None = None,
        ignore: Iterable[str] | None = None,
    ) -> None:
        assert_accessible(response_or_html, select=select, ignore=ignore)
