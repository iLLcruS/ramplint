from __future__ import annotations

import functools
import http.server
import textwrap
import threading
from pathlib import Path

import pytest

from ramplint import lint_source, select_rules


@pytest.fixture
def lint():
    """Lint a template snippet, optionally restricted to some rules.

    Returns a list of ``(code, line)`` tuples for compact assertions.
    """

    def _lint(source: str, *select: str) -> list[tuple[str, int]]:
        rules = select_rules(list(select)) if select else None
        violations = lint_source(textwrap.dedent(source), rules=rules)
        return [(v.code, v.line) for v in violations]

    return _lint


SITES = Path(__file__).parent / "sites"


#: Paths the test web server was asked for, in order.
SITE_REQUESTS: list[str] = []


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - signature from the base class
        SITE_REQUESTS.append(self.path)


@pytest.fixture
def site_requests() -> list[str]:
    """Paths requested from :func:`site_url` during the test."""
    SITE_REQUESTS.clear()
    return SITE_REQUESTS


@pytest.fixture(scope="session")
def site_url():
    """Base URL of a local web server that serves ``tests/sites/``."""
    handler = functools.partial(_QuietHandler, directory=str(SITES))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def chromium_available() -> bool:
    """Skip browser tests when Playwright or Chromium is not installed."""
    from ramplint.browser.options import BrowserOptions
    from ramplint.browser.session import BrowserSession, BrowserUnavailable

    try:
        with BrowserSession(BrowserOptions()):
            pass
    except BrowserUnavailable as exc:
        pytest.skip(f"browser tests need Chromium: {exc}")
    return True
