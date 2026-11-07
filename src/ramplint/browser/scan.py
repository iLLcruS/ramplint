"""Crawl a site: open pages in every viewport, check them and find more pages.

:class:`Crawler` ties the parts together. The :class:`~ramplint.browser.frontier.Frontier`
decides which URL comes next, a :class:`~ramplint.browser.session.BrowserSession`
captures it, the checks find problems in the snapshot and
:mod:`ramplint.browser.discover` finds the links to follow. With
``concurrency`` above 1 several workers, each with its own browser, take URLs
from the same frontier.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from ramplint.browser.checks import (
    ManualCheck,
    check_fragment,
    check_page,
    check_site,
    merge_findings,
)
from ramplint.browser.discover import Action, page_links, parse_sitemap, robots_sitemaps
from ramplint.browser.frontier import Candidate, Coverage, Frontier, Source
from ramplint.browser.options import BrowserOptions
from ramplint.browser.session import BrowserSession, Probe
from ramplint.browser.snapshot import NetworkRecord, PageSnapshot
from ramplint.browser.urls import normalize_url, origin, same_origin, url_key, url_pattern
from ramplint.linter import Violation
from ramplint.project.urls import UrlConf
from ramplint.rules import Rule

#: Called before each page is opened: ``(index, total, url, viewport name)``.
Progress = Callable[[int, int, str, str], None]
#: Called after a page was captured and checked, while the browser is still open.
PageHook = Callable[[BrowserSession, PageSnapshot, list[Violation]], None]
SessionFactory = Callable[[BrowserOptions], BrowserSession]

#: Sitemaps can nest; a crawl reads at most this many sitemap files.
MAX_SITEMAPS = 20


@dataclass
class Endpoint:
    """One entry of the API inventory: requests to the same URL pattern and method."""

    method: str
    #: ``/api/products/<int>/``.
    pattern: str
    urls: set[str] = field(default_factory=set)
    statuses: set[int] = field(default_factory=set)
    content_types: set[str] = field(default_factory=set)
    #: Pages that made the request.
    pages: set[str] = field(default_factory=set)
    failed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "pattern": self.pattern,
            "urls": sorted(self.urls),
            "statuses": sorted(self.statuses),
            "content_types": sorted(self.content_types),
            "pages": sorted(self.pages),
            "failed": self.failed,
        }


@dataclass
class ScanResult:
    snapshots: list[PageSnapshot] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    coverage: list[Coverage] = field(default_factory=list)
    endpoints: list[Endpoint] = field(default_factory=list)
    #: ``hx-post`` and similar requests controls would send; never sent.
    actions: list[Action] = field(default_factory=list)
    #: HTML fragments (``hx-get``, ``fetch``) that were checked.
    fragments: list[str] = field(default_factory=list)
    #: What the rules could not decide (text over images...).
    manual: list[ManualCheck] = field(default_factory=list)

    @property
    def pages_checked(self) -> int:
        """URLs that loaded as HTML in at least one viewport."""
        return len({s.url for s in self.snapshots if s.is_html})

    @property
    def failed(self) -> list[PageSnapshot]:
        return [s for s in self.snapshots if not s.ok]


class ApiInventory:
    """XHR and ``fetch`` requests grouped by method and URL pattern."""

    def __init__(self) -> None:
        self._endpoints: dict[tuple[str, str], Endpoint] = {}

    def add(self, page: str, record: NetworkRecord) -> None:
        pattern = urlsplit(url_pattern(record.url)).path or "/"
        if not same_origin(record.url, page):
            pattern = url_pattern(record.url)
        endpoint = self._endpoints.setdefault(
            (record.method, pattern), Endpoint(record.method, pattern)
        )
        endpoint.urls.add(record.url)
        endpoint.pages.add(page)
        if record.status is None:
            endpoint.failed = True
        else:
            endpoint.statuses.add(record.status)
        if record.content_type:
            endpoint.content_types.add(record.content_type.split(";")[0].strip())

    def endpoints(self) -> list[Endpoint]:
        return sorted(self._endpoints.values(), key=lambda e: (e.pattern, e.method))


class Crawler:
    """Open pages, check them and follow their links until the budget is used up."""

    def __init__(
        self,
        rules: Iterable[Rule],
        options: BrowserOptions,
        *,
        urlconf: UrlConf | None = None,
        login_path: str | None = None,
        progress: Progress | None = None,
        session_factory: SessionFactory | None = None,
        probes: Sequence[Probe] = (),
        on_page: PageHook | None = None,
    ) -> None:
        self.rules = list(rules)
        self.options = options
        self.urlconf = urlconf
        self.login_path = login_path
        self.progress = progress
        self.session_factory = session_factory or BrowserSession
        self.probes = probes
        self.on_page = on_page
        self.inventory = ApiInventory()
        self._result = ScanResult()
        self._violations: list[Violation] = []
        self._actions: dict[tuple[str, str], Action] = {}
        self._fragments: set[str] = set()
        self._lock = threading.Lock()
        self._work = threading.Condition(self._lock)
        self._in_flight = 0
        self._opened = 0
        self._stopped = False
        self.frontier: Frontier | None = None

    # -- running ---------------------------------------------------------------
    def run(self, start_urls: Sequence[str], extra_urls: Sequence[str] = ()) -> ScanResult:
        """Crawl from ``start_urls``; ``extra_urls`` (URLconf, samples) come next.

        Raises :class:`~ramplint.browser.session.BrowserUnavailable` when the
        browser cannot start; problems with single pages are recorded instead.
        """
        self.frontier = Frontier(start_urls[0], self.options, self.urlconf, self.login_path)
        for url in start_urls:
            self.frontier.add(url, 0, Source.START)
        if self.options.crawl:
            for url in extra_urls:
                self.frontier.add(url, 1, Source.URLCONF)
        workers = max(1, self.options.concurrency)
        # The first worker reads the sitemaps before anyone takes a URL.
        self._in_flight = 1 if self.options.crawl else 0
        if workers == 1:
            self._work_loop(first=True)
        else:
            self._run_threads(workers)
        return self._finish()

    def _run_threads(self, workers: int) -> None:
        errors: list[BaseException] = []

        def target(first: bool) -> None:
            try:
                self._work_loop(first)
            except BaseException as exc:  # noqa: BLE001 - re-raised in the main thread
                errors.append(exc)
                with self._work:
                    self._stopped = True
                    self._work.notify_all()

        threads = [
            threading.Thread(target=target, args=(index == 0,), name=f"ramplint-{index}")
            for index in range(workers)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if errors:
            raise errors[0]

    def _work_loop(self, first: bool) -> None:
        with self.session_factory(self.options) as session:
            if first and self.options.crawl:
                try:
                    self._read_sitemaps(session)
                finally:
                    self._done()
            visited = 0
            while (candidate := self._next()) is not None:
                try:
                    if visited and self.options.delay:
                        time.sleep(self.options.delay / 1000)
                    self._visit(session, candidate)
                    visited += 1
                finally:
                    self._done()

    def _next(self) -> Candidate | None:
        """The next URL; waits while other workers may still find more."""
        assert self.frontier is not None
        with self._work:
            while not self._stopped:
                candidate = self.frontier.pop()
                if candidate is not None:
                    self._in_flight += 1
                    self._opened += 1
                    return candidate
                if self._in_flight == 0:
                    return None
                self._work.wait()
            return None

    def _done(self) -> None:
        with self._work:
            self._in_flight -= 1
            self._work.notify_all()

    # -- one page --------------------------------------------------------------
    def _visit(self, session: BrowserSession, candidate: Candidate) -> None:
        assert self.frontier is not None
        snapshots = []
        for viewport in self.options.viewports:
            if self.progress is not None:
                with self._lock:
                    total = max(self._opened + self.frontier.pending, self._opened)
                    total = min(total, self.options.max_pages)
                self.progress(self._opened, total, candidate.url, viewport.name)
            snapshot = session.capture(candidate.url, viewport, self.probes)
            checked = check_page(snapshot, self.rules)
            if self.options.save_snapshots:
                snapshot.save(Path(self.options.save_snapshots) / snapshot.folder_name())
            if self.on_page is not None:
                self.on_page(session, snapshot, checked.violations)
            # Screenshots are large; keep them only while they are needed.
            snapshot.screenshot = snapshot.full_screenshot = None
            for state in snapshot.states:
                state.page.screenshot = None
            snapshots.append(snapshot)
            with self._lock:
                self._violations.extend(checked.violations)
                self._result.manual.extend(checked.manual)
        primary = snapshots[0]
        self.frontier.record(candidate, primary)
        if primary.ok and not primary.is_html:
            # An endpoint opened as a page (``/api/items/`` from the URLconf).
            record = NetworkRecord("GET", candidate.url, primary.status, primary.content_type)
            with self._lock:
                self.inventory.add(candidate.url, record)
        with self._lock:
            self._result.snapshots.extend(snapshots)
        if primary.is_html and not self.frontier.is_login_redirect(primary):
            self._discover(session, candidate, primary)

    def _discover(self, session: BrowserSession, candidate: Candidate, page: PageSnapshot) -> None:
        assert self.frontier is not None
        found = page_links(page.html, page.final_url or page.url)
        fragments = [link.url for link in found.links if link.fragment]
        if self.options.crawl:
            for link in found.links:
                if not link.fragment:
                    self.frontier.add(link.url, candidate.depth + 1, Source.LINK, candidate.url)
        with self._lock:
            for action in found.actions:
                self._actions.setdefault((action.method, action.url), action)
            for record in page.requests:
                self.inventory.add(page.url, record)
        fragments += [
            r.url for r in page.requests if r.method == "GET" and r.is_html and r.status == 200
        ]
        for url in fragments:
            self._check_fragment(session, url)

    def _check_fragment(self, session: BrowserSession, url: str) -> None:
        assert self.frontier is not None
        normalized = normalize_url(url)
        if normalized is None or not same_origin(normalized, self.frontier.start_url):
            return
        if self.options.denied(normalized):
            return
        with self._lock:
            key = url_key(normalized)
            if key in self._fragments or len(self._fragments) >= self.options.max_pages:
                return
            self._fragments.add(key)
        fetched = session.fetch(normalized)
        if fetched is None or not fetched.ok or "html" not in fetched.content_type:
            return
        violations = check_fragment(normalized, fetched.text, self.rules)
        with self._lock:
            self._result.fragments.append(normalized)
            self._violations.extend(violations)

    def _read_sitemaps(self, session: BrowserSession) -> None:
        assert self.frontier is not None
        root = origin(self.frontier.start_url)
        queue = [f"{root}/sitemap.xml"]
        robots = session.fetch(f"{root}/robots.txt")
        if robots is not None and robots.ok:
            queue = robots_sitemaps(robots.text, root) or queue
        seen: set[str] = set()
        while queue and len(seen) < MAX_SITEMAPS:
            url = queue.pop(0)
            if url in seen or not same_origin(url, root):
                continue
            seen.add(url)
            fetched = session.fetch(url)
            if fetched is None or not fetched.ok:
                continue
            sitemap = parse_sitemap(fetched.text, url)
            queue.extend(sitemap.sitemaps)
            self.frontier.add_all(sitemap.pages, 1, Source.SITEMAP)

    def _finish(self) -> ScanResult:
        assert self.frontier is not None
        result = self._result
        primary = self.options.viewports[0].name
        pages = [s for s in result.snapshots if s.viewport == primary]
        self._violations.extend(check_site(pages, self.rules))
        result.violations = merge_findings(self._violations)
        result.coverage = self.frontier.sorted_coverage()
        result.endpoints = self.inventory.endpoints()
        result.actions = sorted(self._actions.values(), key=lambda a: (a.url, a.method))
        result.fragments.sort()
        return result


def scan(
    urls: Sequence[str],
    rules: Iterable[Rule],
    options: BrowserOptions,
    progress: Progress | None = None,
    session_factory: SessionFactory | None = None,
) -> ScanResult:
    """Check ``urls`` (and, with ``options.crawl``, the pages they link to)."""
    return Crawler(rules, options, progress=progress, session_factory=session_factory).run(urls)
