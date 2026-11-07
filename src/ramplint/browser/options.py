"""Options of the browser scan mode (command line and ``[tool.ramplint.browser]``)."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit

#: Named viewports. ``mobile`` emulates a phone, so ``<meta name="viewport">`` applies.
VIEWPORT_PRESETS: dict[str, tuple[int, int, bool]] = {
    "desktop": (1280, 800, False),
    "tablet": (768, 1024, True),
    "mobile": (390, 844, True),
}

#: Image formats for screenshots. JPEG is the default: full-page shots are large.
SCREENSHOT_FORMATS = ("jpeg", "png")

_SIZE_RE = re.compile(r"^(\d{2,5})x(\d{2,5})$")


@dataclass(frozen=True)
class Viewport:
    name: str
    width: int
    height: int
    mobile: bool = False


def parse_viewport(value: str) -> Viewport:
    """``desktop``, ``tablet``, ``mobile`` or ``WIDTHxHEIGHT`` (e.g. ``320x640``)."""
    text = value.strip().lower()
    if text in VIEWPORT_PRESETS:
        width, height, mobile = VIEWPORT_PRESETS[text]
        return Viewport(text, width, height, mobile)
    match = _SIZE_RE.match(text)
    if match is None:
        presets = ", ".join(VIEWPORT_PRESETS)
        raise ValueError(f"invalid viewport {value!r} (use {presets} or WIDTHxHEIGHT)")
    width, height = int(match.group(1)), int(match.group(2))
    return Viewport(text, width, height, mobile=width < 600)


def is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def url_matches(url: str, patterns: Sequence[str]) -> bool:
    """Does ``url`` match one of the glob ``patterns``?

    A pattern with ``://`` is matched against the whole URL
    (``https://example.com/admin/*``), any other pattern against the path and
    query (``/admin/*``, ``*/delete/*``, ``*?page=*``).
    """
    parts = urlsplit(url)
    local = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    for pattern in patterns:
        target = url if "://" in pattern else local
        if fnmatch.fnmatchcase(target, pattern):
            return True
    return False


#: URLs that are never opened: visiting them ends the session or changes data,
#: and the admin is not the site's audience. ``deny`` in the configuration adds
#: to these.
DEFAULT_DENY = (
    "*/logout*",
    "*/log-out*",
    "*/signout*",
    "*/sign-out*",
    "*/delete*",
    "*/remove*",
    "/admin/*",
)


@dataclass
class BrowserOptions:
    viewports: list[Viewport] = field(default_factory=lambda: [parse_viewport("desktop")])
    #: Seconds to wait for one page (load, network idle and ``wait_for``).
    timeout: float = 30.0
    #: Milliseconds to wait between two pages.
    delay: int = 0
    headed: bool = False
    #: CSS selector that must appear before the page is checked.
    wait_for: str | None = None
    #: Write every page snapshot to this folder (for debugging and test fixtures).
    save_snapshots: str | None = None
    #: ``jpeg`` (quality 70) or ``png``.
    screenshot_format: str = "jpeg"
    #: Start page when no URL is given on the command line.
    base_url: str | None = None
    #: Most pages to check in one run.
    max_pages: int = 50
    #: Most pages to check per URL pattern (``/products/<id>/``) when crawling.
    per_pattern: int = 2
    #: Follow links from the given pages. ``False`` checks only the given URLs.
    crawl: bool = True
    #: Pages opened at the same time, each worker with its own browser.
    concurrency: int = 1
    #: Menus, dialogs, tabs and ``<details>`` opened and checked per page.
    max_states: int = 10
    #: Saved logins (``--auth``), one scan per file.
    auth: list[str] = field(default_factory=list)
    #: The saved login of the current scan (Playwright storage state file).
    storage_state: str | None = None
    #: Only URLs matching one of these globs are checked (empty: all).
    include: list[str] = field(default_factory=list)
    #: URLs matching one of these globs are not checked.
    exclude: list[str] = field(default_factory=list)
    #: URLs that are never opened, not even when given on the command line.
    deny: list[str] = field(default_factory=lambda: list(DEFAULT_DENY))
    #: Example paths for URL patterns with parameters, by pattern name.
    samples: dict[str, list[str]] = field(default_factory=dict)

    def denied(self, url: str) -> bool:
        return url_matches(url, self.deny)

    def allowed(self, url: str) -> bool:
        """Should ``url`` be checked (include, exclude and deny)?"""
        if self.denied(url) or url_matches(url, self.exclude):
            return False
        return not self.include or url_matches(url, self.include)
