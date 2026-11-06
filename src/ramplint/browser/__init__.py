"""Browser scan mode: open a running site in Chromium and check the rendered pages.

Needs the optional ``browser`` extra::

    pip install "ramplint[browser]"
    playwright install chromium

Everything that talks to the browser lives in :mod:`ramplint.browser.session`;
the checks work on :class:`~ramplint.browser.snapshot.PageSnapshot` objects, so
they can be tested (and reports regenerated) without a browser.
"""

from __future__ import annotations

from ramplint.browser.options import BrowserOptions, Viewport, is_url, parse_viewport
from ramplint.browser.session import BrowserUnavailable
from ramplint.browser.snapshot import ElementInfo, PageSnapshot

__all__ = [
    "BrowserOptions",
    "BrowserUnavailable",
    "ElementInfo",
    "PageSnapshot",
    "Viewport",
    "is_url",
    "parse_viewport",
]
