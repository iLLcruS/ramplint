"""Browser mode against a real Chromium and a local web server.

Skipped when Playwright or Chromium is not installed::

    pip install -e ".[dev,browser]"
    playwright install chromium
"""

from __future__ import annotations

import socket

import pytest

from ramplint.browser.options import BrowserOptions, parse_viewport
from ramplint.browser.session import BrowserSession
from ramplint.browser.snapshot import PageSnapshot
from ramplint.rules import select_rules

pytestmark = [pytest.mark.browser, pytest.mark.usefixtures("chromium_available")]

DESKTOP = parse_viewport("desktop")


@pytest.fixture(scope="module")
def session():
    with BrowserSession(BrowserOptions(timeout=10)) as browser:
        yield browser


@pytest.fixture(scope="module")
def index(session, site_url) -> PageSnapshot:
    return session.capture(f"{site_url}/basic/index.html", DESKTOP)


def by_id(snapshot: PageSnapshot, element_id: str):
    return next(e for e in snapshot.elements.values() if e.selector == f"#{element_id}")


def test_page_is_captured(index, site_url):
    assert index.ok and index.is_html
    assert index.status == 200
    assert index.title == "Shop"
    assert index.final_url == f"{site_url}/basic/index.html"
    assert index.page_size[0] == 1280
    assert 'data-rl-node="1"' in index.html
    assert index.screenshot.startswith(b"\xff\xd8")  # JPEG
    assert index.full_screenshot.startswith(b"\xff\xd8")


def test_elements_have_boxes_styles_and_names(index):
    button = by_id(index, "named-by-js")
    assert button.tag == "button" and button.visible
    assert button.box[2] > 0 and button.box[3] > 0
    assert button.styles["display"]
    assert button.role == "button" and button.name == "Open menu"
    assert by_id(index, "hidden-img").visible is False
    assert by_id(index, "emptied-by-js").name == ""


def test_console_errors_are_recorded(index):
    # The page loads images that do not exist.
    assert any("404" in error for error in index.console_errors)


def test_rendered_page_problems(index):
    from ramplint.browser.checks import check_snapshot

    found = {(v.code, v.selector) for v in check_snapshot(index, select_rules())}
    assert found == {
        ("RL501", "#emptied-by-js"),
        ("RL502", "#empty-link"),
        ("RL101", "#no-alt"),
        ("RL101", "#added-img"),
    }


def test_wait_for(session, site_url, monkeypatch):
    monkeypatch.setattr(session.options, "wait_for", "#ready")
    snapshot = session.capture(f"{site_url}/basic/slow.html", DESKTOP)
    assert snapshot.ok and "#ready" in {e.selector for e in snapshot.elements.values()}


def test_wait_for_times_out(session, site_url, monkeypatch):
    monkeypatch.setattr(session.options, "wait_for", "#never")
    monkeypatch.setattr(session.options, "timeout", 1)
    snapshot = session.capture(f"{site_url}/basic/clean.html", DESKTOP)
    assert snapshot.error == "'#never' did not appear in 1s"


def test_load_timeout(session, monkeypatch):
    with socket.socket() as server:  # accepts the connection, never answers
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        monkeypatch.setattr(session.options, "timeout", 1)
        snapshot = session.capture(f"http://127.0.0.1:{port}/", DESKTOP)
    assert snapshot.error == "timed out after 1s"


def test_connection_refused(session):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    snapshot = session.capture(f"http://127.0.0.1:{port}/", DESKTOP)
    assert snapshot.error.startswith("net::ERR_CONNECTION_REFUSED")
    assert not snapshot.ok


def test_not_html(session, site_url):
    snapshot = session.capture(f"{site_url}/basic/data.json", DESKTOP)
    assert snapshot.ok and not snapshot.is_html
    assert snapshot.content_type == "application/json"
    assert snapshot.elements == {}


def test_http_error_page_is_still_checked(session, site_url):
    snapshot = session.capture(f"{site_url}/basic/missing.html", DESKTOP)
    assert snapshot.status == 404 and snapshot.is_html


def test_mobile_viewport(session, site_url):
    snapshot = session.capture(f"{site_url}/basic/index.html", parse_viewport("mobile"))
    assert snapshot.page_size[0] == 390
