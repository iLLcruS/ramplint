"""Whole scans and the command line against a real Chromium.

Each test starts its own browser, so this module must not share a session with
other tests (Playwright's sync API allows one running instance per thread).
"""

from __future__ import annotations

import pytest

from ramplint.browser.options import BrowserOptions, parse_viewport
from ramplint.browser.scan import scan
from ramplint.browser.session import BrowserSession, BrowserUnavailable
from ramplint.browser.snapshot import PageSnapshot
from ramplint.cli import EXIT_VIOLATIONS, main
from ramplint.rules import select_rules

pytestmark = [pytest.mark.browser, pytest.mark.usefixtures("chromium_available")]

DESKTOP = parse_viewport("desktop")


def test_scan_merges_viewports(site_url):
    options = BrowserOptions(timeout=10, viewports=[DESKTOP, parse_viewport("mobile")], delay=1)
    seen = []
    result = scan(
        [f"{site_url}/basic/index.html", f"{site_url}/basic/clean.html"],
        select_rules(["RL101"]),
        options,
        progress=lambda *args: seen.append(args),
    )
    assert len(seen) == 4 and result.pages_checked == 2
    assert {(v.selector, v.viewport) for v in result.violations} == {
        ("#no-alt", "desktop,mobile"),
        ("#added-img", "desktop,mobile"),
    }
    assert all(s.screenshot is None for s in result.snapshots)  # freed after checking


def test_cli_end_to_end(site_url, tmp_path, capsys):
    snapshots = tmp_path / "snapshots"
    code = main([f"{site_url}/basic/index.html", "--no-color", "--save-snapshots", str(snapshots)])
    assert code == EXIT_VIOLATIONS
    out = capsys.readouterr().out
    assert "#emptied-by-js: RL501" in out
    assert "Found 4 problems in 1 of 1 page." in out
    saved = PageSnapshot.load(next(snapshots.iterdir()))
    assert saved.title == "Shop" and saved.screenshot


def test_chromium_missing(monkeypatch):
    import playwright.sync_api

    class FakeChromium:
        def launch(self, headless):
            raise Exception("BrowserType.launch: Executable doesn't exist at /x/chrome")

    class FakePlaywright:
        chromium = FakeChromium()
        stopped = False

        def start(self):
            return self

        def stop(self):
            FakePlaywright.stopped = True

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: FakePlaywright())
    with pytest.raises(BrowserUnavailable, match="playwright install chromium"):
        BrowserSession(BrowserOptions()).__enter__()
    assert FakePlaywright.stopped


def test_chromium_fails_to_start(monkeypatch):
    import playwright.sync_api

    class FakePlaywright:
        class chromium:  # noqa: N801
            @staticmethod
            def launch(headless):
                raise Exception("Host system is missing dependencies\n=====\nmore")

        def start(self):
            return self

        def stop(self):
            pass

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: FakePlaywright())
    with pytest.raises(BrowserUnavailable, match="^Host system is missing dependencies$"):
        BrowserSession(BrowserOptions()).__enter__()
