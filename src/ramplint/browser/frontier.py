"""Which page to open next.

A site with 10 000 product pages has one product template. The frontier spends
the page budget on different templates, not on more of the same: every URL is
matched to its URL pattern (from the Django URLconf, or inferred from the
path), at most ``per_pattern`` URLs of a pattern are opened, and patterns that
were not visited yet come first. It also keeps the crawl safe (same origin,
deny list) and records what happened to every pattern for the report.
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from fnmatch import fnmatchcase
from urllib.parse import urlsplit

from ramplint.browser.options import BrowserOptions
from ramplint.browser.snapshot import PageSnapshot
from ramplint.browser.urls import normalize_url, path_and_query, placeholder, same_origin, url_key
from ramplint.project.urls import UrlConf, UrlPattern

#: Words in a URL pattern name that mark pages a crawler must not open.
DENIED_NAME_WORDS = frozenset({"logout", "signout", "delete", "remove"})
_NAME_SPLIT_RE = re.compile(r"[:_\-./]")
#: Siblings needed before a varying last segment is treated as a parameter.
SLUG_SIBLINGS = 5


class Source(IntEnum):
    """Where a URL came from; lower values are visited first."""

    START = 0
    URLCONF = 1
    SAMPLE = 2
    SITEMAP = 3
    LINK = 4


class Status:
    """Coverage of a URL pattern in the report."""

    SCANNED = "scanned"
    NEEDS_SAMPLE = "needs sample"
    NEEDS_LOGIN = "needs login"
    DENIED = "denied"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class Candidate:
    url: str
    key: str
    depth: int
    source: Source
    order: int
    referrer: str | None = None


@dataclass
class Coverage:
    """What the crawl did with one URL pattern."""

    #: ``/products/<int:pk>/`` (URLconf) or ``/products/{slug}/`` (inferred).
    route: str
    name: str | None = None
    #: ``catalog/urls.py:9`` for URLconf patterns.
    source: str | None = None
    has_parameters: bool = False
    found: set[str] = field(default_factory=set)
    scanned: list[str] = field(default_factory=list)
    #: URL -> HTTP status (or the load error).
    results: dict[str, str] = field(default_factory=dict)
    #: URL -> where it redirected to.
    redirects: dict[str, str] = field(default_factory=dict)
    login_required: list[str] = field(default_factory=list)
    #: URL -> content type of responses that are not pages (JSON, files).
    not_pages: dict[str, str] = field(default_factory=dict)
    denied: bool = False

    @property
    def status(self) -> str:
        if self.denied:
            return Status.DENIED
        if self.scanned:
            return Status.SCANNED
        if self.login_required:
            return Status.NEEDS_LOGIN
        if self.results:
            return Status.ERROR
        if self.not_pages:
            return Status.SKIPPED
        if not self.found:
            return Status.NEEDS_SAMPLE if self.has_parameters else Status.SKIPPED
        return Status.SKIPPED

    @property
    def summary(self) -> str:
        """``scanned (2 of 500)``, ``needs sample``, ``error (HTTP 500)``..."""
        status = self.status
        if status == Status.SCANNED:
            return f"{status} ({len(self.scanned)} of {max(len(self.found), 1)})"
        if status == Status.ERROR:
            return f"{status} ({', '.join(sorted(set(self.results.values())))})"
        if status == Status.SKIPPED and self.not_pages:
            kinds = ", ".join(sorted(set(self.not_pages.values())))
            return f"{status} (not a page: {kinds})"
        if status == Status.SKIPPED and self.found:
            return f"{status} ({len(self.found)} found, page budget used up)"
        return status

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "name": self.name,
            "source": self.source,
            "status": self.status,
            "summary": self.summary,
            "found": len(self.found),
            "scanned": self.scanned,
            "results": self.results,
            "redirects": self.redirects,
            "not_pages": self.not_pages,
        }


class PatternInference:
    """URL patterns of sites without a URLconf, learned from the URLs seen.

    Ids (numbers, UUIDs, dates, hashes) are recognised on their own. A last
    segment that varies across many sibling URLs, mostly slug-like
    (``hello-world``), becomes ``{slug}``: ``/blog/a-post/`` and
    ``/blog/another-one/`` are one pattern.
    """

    def __init__(self) -> None:
        self._children: dict[tuple[str, ...], set[str]] = defaultdict(set)

    @staticmethod
    def _segments(path: str) -> tuple[list[str], bool]:
        segments = [s for s in path.split("/") if s]
        return [placeholder(s) or s for s in segments], path.endswith("/")

    def observe(self, path: str) -> None:
        segments, _ = self._segments(path)
        if len(segments) >= 2:
            self._children[tuple(segments[:-1])].add(segments[-1])

    def _is_slug_family(self, parent: tuple[str, ...]) -> bool:
        children = self._children.get(parent, set())
        if len(children) < SLUG_SIBLINGS:
            return False
        sluggy = sum(1 for c in children if "-" in c or any(ch.isdigit() for ch in c))
        return sluggy * 5 >= len(children) * 3  # at least 60 %

    def pattern(self, path: str) -> str:
        segments, trailing = self._segments(path)
        last_is_id = bool(segments) and segments[-1].startswith("<")
        if len(segments) >= 2 and not last_is_id and self._is_slug_family(tuple(segments[:-1])):
            segments[-1] = "{slug}"
        route = "/" + "/".join(segments)
        return route + "/" if trailing and segments else route


class Frontier:
    """Thread-safe queue of URLs to open, with a budget per pattern and in total."""

    def __init__(
        self,
        start_url: str,
        options: BrowserOptions,
        urlconf: UrlConf | None = None,
        login_path: str | None = None,
    ) -> None:
        self.start_url = start_url
        self.options = options
        self.urlconf = urlconf
        self.login_path = login_path
        self.inference = PatternInference()
        self.coverage: dict[str, Coverage] = {}
        self._pending: dict[str, Candidate] = {}
        self._seen: set[str] = set()
        self._opened: dict[str, int] = defaultdict(int)
        self._pages = 0
        self._order = 0
        self._lock = threading.RLock()
        if urlconf is not None:
            for pattern in urlconf.patterns:
                self._coverage_for(pattern.route, pattern)

    # -- patterns --------------------------------------------------------------
    def _url_pattern(self, url: str) -> UrlPattern | None:
        if self.urlconf is None:
            return None
        return self.urlconf.match(urlsplit(url).path)

    def pattern_of(self, url: str) -> str:
        """The route of the URL pattern ``url`` belongs to (query strings ignored)."""
        matched = self._url_pattern(url)
        if matched is not None:
            return matched.route
        return self.inference.pattern(urlsplit(url).path or "/")

    def _coverage_for(self, route: str, pattern: UrlPattern | None = None) -> Coverage:
        coverage = self.coverage.get(route)
        if coverage is None:
            coverage = Coverage(route)
            if pattern is not None:
                coverage.name = pattern.name
                coverage.source = f"{pattern.source}:{pattern.line}"
                coverage.has_parameters = bool(pattern.parameters) or not pattern.is_static
                coverage.denied = self._name_denied(pattern.name)
            self.coverage[route] = coverage
        return coverage

    def _name_denied(self, name: str | None) -> bool:
        if not name:
            return False
        if DENIED_NAME_WORDS & set(_NAME_SPLIT_RE.split(name.lower())):
            return True
        return any(fnmatchcase(name, pattern) for pattern in self.options.deny)

    # -- adding ----------------------------------------------------------------
    def add(
        self,
        url: str,
        depth: int = 0,
        source: Source = Source.LINK,
        referrer: str | None = None,
    ) -> bool:
        """Queue ``url``; ``False`` when it is not followed (other origin, denied...)."""
        normalized = normalize_url(url, self.start_url)
        if normalized is None or not same_origin(normalized, self.start_url):
            return False
        key = url_key(normalized)
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            self.inference.observe(urlsplit(normalized).path)
            pattern = self._url_pattern(normalized)
            coverage = self._coverage_for(self.pattern_of(normalized), pattern)
            coverage.found.add(normalized)
            if self._denied(normalized, pattern):
                coverage.denied = True
                return False
            if not self.options.allowed(normalized) and source != Source.START:
                return False
            self._order += 1
            self._pending[key] = Candidate(normalized, key, depth, source, self._order, referrer)
            return True

    def add_all(self, urls: Iterable[str], depth: int, source: Source) -> None:
        for url in urls:
            self.add(url, depth, source)

    def _denied(self, url: str, pattern: UrlPattern | None) -> bool:
        if self.options.denied(url):
            return True
        return pattern is not None and self._name_denied(pattern.name)

    # -- taking ----------------------------------------------------------------
    def _priority(self, candidate: Candidate) -> tuple[int, int, int, int]:
        visited = self._opened[self.pattern_of(candidate.url)]
        is_start = 0 if candidate.source == Source.START else 1
        return (is_start, visited, candidate.depth, candidate.order)

    def pop(self) -> Candidate | None:
        """The next URL to open, or ``None`` when the budget or the queue is used up."""
        with self._lock:
            if self._pages >= self.options.max_pages:
                return None
            while self._pending:
                candidate = min(self._pending.values(), key=self._priority)
                del self._pending[candidate.key]
                route = self.pattern_of(candidate.url)
                limit = self.options.per_pattern
                if candidate.source != Source.START and self._opened[route] >= limit:
                    continue  # stays "found" in the coverage, not scanned
                self._opened[route] += 1
                self._pages += 1
                return candidate
            return None

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    # -- results ---------------------------------------------------------------
    def is_login_redirect(self, snapshot: PageSnapshot) -> bool:
        if not self.login_path or not snapshot.final_url:
            return False
        final = urlsplit(snapshot.final_url).path
        asked = urlsplit(snapshot.url).path
        return final.rstrip("/") == self.login_path.rstrip("/") and asked != final

    def record(self, candidate: Candidate, snapshot: PageSnapshot) -> None:
        """What opening ``candidate`` gave, for the coverage report."""
        with self._lock:
            coverage = self._coverage_for(self.pattern_of(candidate.url))
            final = normalize_url(snapshot.final_url) if snapshot.final_url else None
            if final and url_key(final) != candidate.key:
                coverage.redirects[candidate.url] = final
            if self.is_login_redirect(snapshot):
                coverage.login_required.append(candidate.url)
            elif not snapshot.ok:
                coverage.results[candidate.url] = snapshot.error
            elif snapshot.status is not None and snapshot.status >= 400:
                coverage.results[candidate.url] = f"HTTP {snapshot.status}"
            elif snapshot.is_html:
                coverage.scanned.append(candidate.url)
            else:
                kind = snapshot.content_type.split(";")[0].strip() or "not HTML"
                coverage.not_pages[candidate.url] = kind

    def sorted_coverage(self) -> list[Coverage]:
        """Coverage of every pattern, by route."""
        with self._lock:
            return sorted(self.coverage.values(), key=lambda c: c.route)


def start_urls(
    urlconf: UrlConf, samples: dict[str, list[str]], base: str
) -> tuple[list[str], list[str]]:
    """URLs of the URLconf patterns without parameters and of the configured samples.

    Also returns the sample names that match no URL pattern, to warn about.
    """
    paths = list(urlconf.start_paths)
    unknown = []
    for name, examples in samples.items():
        if urlconf.by_name(name) is None:
            unknown.append(name)
        paths.extend(examples)
    urls = (normalize_url(path, base) for path in paths)
    return [url for url in dict.fromkeys(urls) if url], unknown


def describe(url: str) -> str:
    """``/products/1/`` for messages."""
    return path_and_query(url)
