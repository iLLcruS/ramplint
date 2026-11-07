"""A fake browser for crawl tests: a site described as a dict, no Chromium."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from ramplint.browser.options import BrowserOptions
from ramplint.browser.session import Fetched
from ramplint.browser.snapshot import NetworkRecord, PageSnapshot

PAGE_HTML = (
    '<html lang="en"><head><title>Page</title></head><body><main><h1>Hi</h1></main></body></html>'
)


@dataclass
class FakePage:
    html: str = PAGE_HTML
    status: int = 200
    content_type: str = "text/html"
    #: Final URL after a redirect.
    redirect: str | None = None
    requests: list[NetworkRecord] = field(default_factory=list)
    error: str = ""


def links_page(*hrefs: str, title: str = "Page", extra: str = "") -> FakePage:
    links = "".join(f'<a href="{href}">{href}</a>' for href in hrefs)
    return FakePage(
        html=(
            f'<html lang="en"><head><title>{title}</title></head>'
            f"<body><main><h1>{title}</h1>{links}{extra}</main></body></html>"
        )
    )


class FakeBrowser:
    """``site`` maps URLs to pages (or callables making one); ``files`` to fetch results."""

    def __init__(
        self,
        site: dict[str, FakePage | Callable[[str], FakePage]],
        files: dict[str, Fetched] | None = None,
    ) -> None:
        self.site = site
        self.files = files or {}
        self.opened: list[str] = []
        self.fetched: list[str] = []
        self.sessions = 0
        self._lock = threading.Lock()

    def factory(self, options: BrowserOptions) -> FakeSession:
        with self._lock:
            self.sessions += 1
        return FakeSession(self, options)


class FakeSession:
    def __init__(self, browser: FakeBrowser, options: BrowserOptions) -> None:
        self.browser = browser
        self.options = options

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def capture(self, url, viewport, probes=()) -> PageSnapshot:
        with self.browser._lock:
            self.browser.opened.append(url)
        entry = self.browser.site.get(url)
        if entry is None:
            entry = FakePage(html="<html><body>Not found</body></html>", status=404)
        page = entry(url) if callable(entry) else entry
        title = re.search(r"<title>(.*?)</title>", page.html, re.S)
        return PageSnapshot(
            url=url,
            viewport=viewport.name,
            title=title.group(1) if title else "",
            final_url=page.redirect or url,
            status=page.status,
            content_type=page.content_type,
            html=page.html,
            requests=list(page.requests),
            error=page.error,
        )

    def fetch(self, url: str) -> Fetched | None:
        with self.browser._lock:
            self.browser.fetched.append(url)
        return self.browser.files.get(url)
