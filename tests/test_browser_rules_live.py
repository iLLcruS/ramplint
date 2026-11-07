"""Rendered-page rules and UI states against a real Chromium (tests/sites/rules/)."""

from __future__ import annotations

import pytest

from ramplint.browser.checks import check_page
from ramplint.browser.options import BrowserOptions, parse_viewport
from ramplint.browser.probes import focus_order, probes_for, reflow, ui_states
from ramplint.browser.session import BrowserSession
from ramplint.rules import select_rules

pytestmark = [pytest.mark.browser, pytest.mark.usefixtures("chromium_available")]

DESKTOP = parse_viewport("desktop")
PROBES = (focus_order, reflow, ui_states)


@pytest.fixture(scope="module")
def session():
    with BrowserSession(BrowserOptions(timeout=15)) as browser:
        yield browser


@pytest.fixture(scope="module")
def capture(session, site_url):
    cache = {}

    def _capture(name: str):
        if name not in cache:
            cache[name] = session.capture(f"{site_url}/rules/{name}", DESKTOP, PROBES)
        return cache[name]

    return _capture


def problems(snapshot, *codes):
    result = check_page(snapshot, select_rules(list(codes)))
    return [(v.code, v.selector, v.state) for v in result.violations], result.manual


def test_contrast(capture):
    found, manual = problems(capture("contrast.html"), "RL801")
    assert found == [
        ("RL801", "#low", None),
        ("RL801", "#glass", None),
        ("RL801", "#faded", None),
    ]
    assert [m.selector for m in manual] == ["#hero"]


def test_target_size(capture):
    found, _ = problems(capture("targets.html"), "RL802")
    assert found == [("RL802", "#prev", None), ("RL802", "#next", None)]


def test_reflow(capture):
    found, _ = problems(capture("reflow.html"), "RL803")
    assert found == [("RL803", "#banner", None)]
    assert problems(capture("reflow-ok.html"), "RL803")[0] == []


def test_focus_visible_and_obscured(capture):
    page = capture("focus.html")
    order = [page.element(stop.element).selector for stop in page.focus]
    assert order == ["#plain", "#invisible", "#styled", "#hidden-link"]
    assert problems(page, "RL804")[0] == [("RL804", "#invisible", None)]
    assert problems(page, "RL805")[0] == [("RL805", "#hidden-link", None)]


def test_keyboard_trap(capture):
    page = capture("trap.html")
    assert [page.element(e).selector for e in page.keyboard_trap] == ["#a", "#b"]
    assert problems(page, "RL806")[0] == [("RL806", "#a", None)]


def test_menus_and_dialogs(capture, site_requests):
    page = capture("states.html")
    states = {state.trigger: state for state in page.states}
    assert list(states) == [
        "#menu-toggle",
        "#open-dialog",
        "#broken-toggle",
        "#fake-dialog-open",
        "#sender",
        "#faq > summary",
    ]  # the link that would leave the page is not clicked
    assert states["#menu-toggle"].expanded is True
    assert states["#open-dialog"].dialog.focus_inside  # showModal() moves focus
    assert states["#sender"].blocked == (f"POST {page.url.rsplit('/rules/', 1)[0]}/api/save/",)
    found, _ = problems(page, "RL1", "RL5", "RL806", "RL807")
    menu = 'after clicking "Menu" (#menu-toggle)'
    assert found == [
        ("RL806", "#help", 'after clicking "Help" (#fake-dialog-open)'),
        ("RL807", "#broken-toggle", 'after clicking "More" (#broken-toggle)'),
        ("RL502", "#menu > li:nth-of-type(2) > a", menu),
        ("RL101", "#menu-img", menu),
        ("RL502", "#faq > p > a", 'after clicking "Shipping" (#faq > summary)'),
    ]


def test_nothing_is_sent_or_deleted(session, site_url, site_requests):
    session.capture(f"{site_url}/rules/states.html", DESKTOP, (ui_states,))
    assert not any("delete-account" in path or "api/save" in path for path in site_requests)


def test_max_states(session, site_url, monkeypatch):
    monkeypatch.setattr(session.options, "max_states", 2)
    page = session.capture(f"{site_url}/rules/states.html", DESKTOP, (ui_states,))
    assert len(page.states) == 2


def test_probes_for():
    options = BrowserOptions()
    assert probes_for(select_rules(), options) == [focus_order, reflow, ui_states]
    assert probes_for(select_rules(["RL1"]), BrowserOptions(max_states=0)) == []
    assert probes_for(select_rules(["RL803"]), BrowserOptions(max_states=0)) == [reflow]
