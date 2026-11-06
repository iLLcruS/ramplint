"""Scan a list of URLs: capture each page in each viewport and check it."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ramplint.browser.checks import check_snapshot, merge_viewports
from ramplint.browser.options import BrowserOptions
from ramplint.browser.session import BrowserSession
from ramplint.browser.snapshot import PageSnapshot
from ramplint.linter import Violation
from ramplint.rules import Rule

#: Called before each page is opened: ``(index, total, url, viewport name)``.
Progress = Callable[[int, int, str, str], None]


@dataclass
class ScanResult:
    snapshots: list[PageSnapshot] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    @property
    def pages_checked(self) -> int:
        """URLs that loaded as HTML in at least one viewport."""
        return len({s.url for s in self.snapshots if s.is_html})

    @property
    def failed(self) -> list[PageSnapshot]:
        return [s for s in self.snapshots if not s.ok]


def scan(
    urls: Sequence[str],
    rules: Iterable[Rule],
    options: BrowserOptions,
    progress: Progress | None = None,
    session_factory: Callable[[BrowserOptions], BrowserSession] | None = None,
) -> ScanResult:
    """Open every URL in every viewport and check the rendered pages.

    Raises :class:`~ramplint.browser.session.BrowserUnavailable` when the
    browser cannot start; problems with single pages are recorded instead.
    """
    rules = list(rules)
    result = ResultBuilder(options)
    jobs = [(url, viewport) for url in urls for viewport in options.viewports]
    factory = session_factory or BrowserSession
    with factory(options) as session:
        for index, (url, viewport) in enumerate(jobs, start=1):
            if index > 1 and options.delay:
                time.sleep(options.delay / 1000)
            if progress is not None:
                progress(index, len(jobs), url, viewport.name)
            snapshot = session.capture(url, viewport)
            result.add(snapshot, check_snapshot(snapshot, rules))
    return result.build()


class ResultBuilder:
    def __init__(self, options: BrowserOptions) -> None:
        self.options = options
        self.snapshots: list[PageSnapshot] = []
        self.violations: list[Violation] = []

    def add(self, snapshot: PageSnapshot, violations: list[Violation]) -> None:
        if self.options.save_snapshots:
            snapshot.save(Path(self.options.save_snapshots) / snapshot.folder_name())
        # Screenshots are large; keep them only while they are needed.
        snapshot.screenshot = snapshot.full_screenshot = None
        self.snapshots.append(snapshot)
        self.violations.extend(violations)

    def build(self) -> ScanResult:
        return ScanResult(snapshots=self.snapshots, violations=merge_viewports(self.violations))
