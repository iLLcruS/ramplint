"""Rules on rendered pages, without a browser (hand-made snapshots)."""

from __future__ import annotations

import re

import pytest

from ramplint.browser.checks import browser_rules, check_snapshot, merge_viewports
from ramplint.browser.snapshot import ElementInfo, PageSnapshot
from ramplint.linter import Violation
from ramplint.rules import select_rules

URL = "http://localhost:8000/products/"


def snapshot(html: str, viewport: str = "desktop", **overrides) -> PageSnapshot:
    """Number the elements of ``html`` like collect.js does.

    ``overrides`` maps an element id attribute to ElementInfo fields, e.g.
    ``hidden_img={"visible": False}``.
    """
    elements: dict[str, ElementInfo] = {}
    counter = 0

    def number(match: re.Match) -> str:
        nonlocal counter
        counter += 1
        node_id = str(counter)
        tag = match.group(1)
        id_attr = re.search(r'\bid="([^"]+)"', match.group(0))
        info = ElementInfo(
            id=node_id,
            tag=tag,
            selector=f"#{id_attr.group(1)}" if id_attr else f"{tag}:nth-of-type({counter})",
            box=(10.0, 20.0 * counter, 100.0, 20.0),
            visible=True,
        )
        if id_attr and id_attr.group(1) in overrides:
            for key, value in overrides[id_attr.group(1)].items():
                setattr(info, key, value)
        elements[node_id] = info
        return f'{match.group(0)[:-1]} data-rl-node="{node_id}">'

    numbered = re.sub(r"<([a-z][a-z0-9]*)\b[^>]*>", number, html)
    return PageSnapshot(
        url=URL,
        viewport=viewport,
        final_url=URL,
        status=200,
        content_type="text/html; charset=utf-8",
        html=numbered,
        elements=elements,
    )


def codes(violations: list[Violation]) -> list[str]:
    return [v.code for v in violations]


PAGE = """<!DOCTYPE html>
<html lang="en"><head><title>Shop</title></head><body><main>
<h1>Products</h1>
<img src="a.png" id="logo">
<button id="icon"></button>
</main></body></html>"""


def test_reports_problems_with_url_selector_and_box():
    found = check_snapshot(snapshot(PAGE), select_rules())
    assert codes(found) == ["RL101", "RL501"]
    image = found[0]
    assert image.path == URL and image.url == URL
    assert image.selector == "#logo"
    assert image.viewport == "desktop"
    assert image.bbox is not None and image.bbox[2] == 100.0
    assert image.in_browser


def test_hidden_elements_are_skipped():
    found = check_snapshot(snapshot(PAGE, logo={"visible": False}), select_rules())
    assert codes(found) == ["RL501"]


def test_visibility_does_not_matter_for_document_and_aria_rules():
    html = (
        "<html><head><title>X</title></head><body><main><h1>X</h1>"
        '<div id="d" role="nope"></div></main></body></html>'
    )
    found = check_snapshot(snapshot(html, d={"visible": False}), select_rules())
    assert set(codes(found)) == {"RL601", "RL701"}


def test_accessible_name_from_the_browser_wins():
    found = check_snapshot(snapshot(PAGE, icon={"name": "Open menu"}), select_rules())
    assert codes(found) == ["RL101"]


def test_empty_browser_name_keeps_the_problem():
    found = check_snapshot(snapshot(PAGE, icon={"name": "  "}), select_rules())
    assert "RL501" in codes(found)


def test_template_only_rules_are_not_run():
    rules = select_rules(["RL4"])
    assert {r.code for r in browser_rules(rules)} == {"RL401", "RL402", "RL403"}


def test_inline_suppressions_survive_rendering():
    image = '<img src="a.png" id="logo">'
    html = PAGE.replace(image, f"<!-- ramplint: ignore img-alt -->\n{image}")
    assert codes(check_snapshot(snapshot(html), select_rules())) == ["RL501"]


def test_elements_without_snapshot_data_are_still_reported():
    page = snapshot(PAGE.replace("<img", '<img src="b.png"><img'))
    page.elements.clear()
    found = check_snapshot(page, select_rules(["RL101"]))
    assert [(v.code, v.selector, v.bbox) for v in found] == [("RL101", "img", None)] * 2


@pytest.mark.parametrize(
    "change",
    [
        {"error": "net::ERR_CONNECTION_REFUSED"},
        {"content_type": "application/json"},
        {"html": ""},
    ],
)
def test_pages_that_did_not_load_have_no_problems(change):
    page = snapshot(PAGE)
    for key, value in change.items():
        setattr(page, key, value)
    assert check_snapshot(page, select_rules()) == []


def test_same_element_in_several_viewports_is_one_problem():
    rules = select_rules()
    found = check_snapshot(snapshot(PAGE, "desktop"), rules) + check_snapshot(
        snapshot(PAGE, "mobile"), rules
    )
    merged = merge_viewports(found)
    assert [(v.code, v.viewport) for v in merged] == [
        ("RL101", "desktop,mobile"),
        ("RL501", "desktop,mobile"),
    ]


def test_problem_in_one_viewport_only():
    desktop = check_snapshot(snapshot(PAGE, "desktop", logo={"visible": False}), select_rules())
    mobile = check_snapshot(snapshot(PAGE, "mobile"), select_rules())
    merged = merge_viewports(desktop + mobile)
    assert ("RL101", "mobile") in [(v.code, v.viewport) for v in merged]


def test_template_violations_are_unchanged():
    v = Violation("a.html", 1, 1, "RL101", "img-alt", "msg")
    assert v.to_dict() == {
        "path": "a.html",
        "line": 1,
        "col": 1,
        "code": "RL101",
        "name": "img-alt",
        "message": "msg",
    }
    assert not v.in_browser
    browser = Violation("a.html", 1, 1, "RL101", "img-alt", "msg", url="u", bbox=(1, 2, 3, 4))
    assert browser == v  # browser fields do not take part in comparisons
    assert browser.to_dict()["bbox"] == [1, 2, 3, 4]
