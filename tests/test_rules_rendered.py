"""Rendered-page rules (RL801-RL807) on hand-made snapshots - no browser."""

from __future__ import annotations

import pytest

from ramplint import lint_source
from ramplint.browser.checks import check_page
from ramplint.browser.snapshot import (
    Dialog,
    ElementInfo,
    FocusStop,
    PageSnapshot,
    Reflow,
    TextSample,
    UiState,
)
from ramplint.dom import VOID_ELEMENTS
from ramplint.rules import select_rules

URL = "http://shop.test/"


def snapshot(*elements: tuple[str, str, tuple, dict], body: str = "", **fields) -> PageSnapshot:
    """``elements``: ``(tag, attributes, box, styles)``; ids are their positions + 1."""
    html = ['<html lang="en" data-rl-node="0"><head><title>T</title></head><body><main><h1>T</h1>']
    infos = {}
    for index, (tag, attrs, box, styles) in enumerate(elements, start=1):
        content = "" if tag in VOID_ELEMENTS else f"x</{tag}>"
        html.append(f'<{tag} data-rl-node="{index}" {attrs}>{content}')
        selector = f"#e{index}"
        infos[str(index)] = ElementInfo(str(index), tag, selector, box, True, styles)
    html.append(f"{body}</main></body></html>")
    return PageSnapshot(
        url=URL, viewport="desktop", status=200, content_type="text/html",
        html="".join(html), elements=infos, **fields,
    )  # fmt: skip


def found(page: PageSnapshot, code: str) -> list[tuple[str | None, str]]:
    result = check_page(page, select_rules([code]))
    return [(v.selector, v.message) for v in result.violations]


def test_rules_do_nothing_in_template_mode():
    assert lint_source('<p style="color:#eee">x</p>', rules=select_rules(["RL8"])) == []


# -- RL801 ------------------------------------------------------------------------


def text(element: str, color: str, *backgrounds: str, **fields) -> TextSample:
    values = {"over_image": False, "font_size": 16.0, "font_weight": 400, **fields}
    return TextSample(element, color, tuple(backgrounds), **values)


def test_contrast():
    page = snapshot(*[("p", "", (0, 0, 10, 10), {})] * 6, ("button", "disabled", (0, 0, 1, 1), {}))
    page.texts = [
        text("1", "rgb(34, 34, 34)", "rgb(255, 255, 255)"),
        text("2", "rgb(170, 170, 170)", "rgb(255, 255, 255)"),
        text("3", "rgb(148, 148, 148)", "rgb(255, 255, 255)", font_size=24.0),
        text("4", "rgb(34, 34, 34)", "rgba(0, 0, 0, 0.5)"),
        text("5", "rgb(238, 238, 238)", over_image=True),
        text("6", "rgb(34, 34, 34)", opacity=0.3),
        text("7", "rgb(170, 170, 170)"),
    ]
    result = check_page(page, select_rules(["RL801"]))
    assert [(v.selector, v.message.split(" (")[0]) for v in result.violations] == [
        ("#e2", "Contrast of 2.32:1 is below 4.5:1 for text"),
        ("#e4", "Contrast of 4.00:1 is below 4.5:1 for text"),
        ("#e6", "Contrast of 1.88:1 is below 4.5:1 for text"),
    ]
    assert "(#aaaaaa on #ffffff)" in result.violations[0].message
    assert [(m.selector, m.code) for m in result.manual] == [("#e5", "RL801")]


def test_contrast_unknown_colour_format_needs_a_person():
    page = snapshot(("p", "", (0, 0, 1, 1), {}))
    page.texts = [text("1", "oklch(0.2 0 0)", "rgb(255, 255, 255)")]
    result = check_page(page, select_rules(["RL801"]))
    assert result.violations == [] and len(result.manual) == 1


def test_contrast_skips_hidden_and_unknown_elements():
    page = snapshot(("p", "", (0, 0, 1, 1), {}))
    page.elements["1"].visible = False
    page.texts = [text("1", "rgb(250, 250, 250)"), text("99", "rgb(250, 250, 250)")]
    assert found(page, "RL801") == []


# -- RL802 ------------------------------------------------------------------------


def test_target_size():
    page = snapshot(
        ("button", 'aria-label="a"', (0, 0, 16, 16), {}),  # crowded
        ("button", 'aria-label="b"', (18, 0, 16, 16), {}),  # crowded
        ("button", 'aria-label="c"', (200, 200, 16, 16), {}),  # alone: spacing is enough
        ("a", 'href="/x"', (0, 100, 30, 17), {"display": "inline"}),  # in text below
        ("button", "", (300, 300, 44, 44), {}),  # big
        ("input", 'type="checkbox" id="c"', (0, 400, 13, 13), {}),
        ("label", 'for="c"', (20, 400, 50, 13), {}),
        ("button", "", (0, 500, 40, 21), {"font-size": "13.3333px", "border-top-style": "outset"}),
        ("button", "", (0, 520, 40, 21), {"font-size": "13.3333px", "border-top-style": "outset"}),
        ("input", 'type="hidden"', (0, 0, 0, 0), {}),
        ("span", 'role="button" tabindex="0"', (210, 0, 10, 10), {}),  # crowded by e3? no: far
    )
    page = PageSnapshot(**{**page.__dict__, "html": page.html.replace(
        '<a data-rl-node="4" href="/x">x</a>', '<p>Read <a data-rl-node="4" href="/x">x</a> now</p>'
    )})  # fmt: skip
    selectors = [selector for selector, _ in found(page, "RL802")]
    assert selectors == ["#e1", "#e2"]


def test_target_next_to_a_big_target():
    page = snapshot(
        ("button", 'aria-label="x"', (0, 0, 16, 16), {}),
        ("button", "", (19, 0, 100, 40), {}),
    )
    assert [s for s, _ in found(page, "RL802")] == ["#e1"]
    page.elements["2"].box = (20, 0, 100, 40)  # the 24 px circle just touches it: fine
    assert found(page, "RL802") == []


# -- RL803 ------------------------------------------------------------------------


def test_reflow():
    page = snapshot(("div", 'id="banner"', (0, 0, 640, 20), {}))
    page.elements["1"].selector = "#banner"
    page.reflow = Reflow(320, 648, (("#banner", 648.0),))
    assert found(page, "RL803") == [
        (
            "#banner",
            "At 320 px wide the page scrolls sideways (648 px of content): #banner ends at "
            "648 px; let it wrap or shrink (max-width: 100%)",
        )
    ]
    page.reflow = Reflow(320, 320)
    assert found(page, "RL803") == []
    page.reflow = Reflow(320, 900)  # scrolls, but only inside allowed content
    assert found(page, "RL803") == []


# -- RL804-RL806 ----------------------------------------------------------------------


def test_focus_rules():
    page = snapshot(*[("button", "", (0, 0, 40, 40), {})] * 3)
    page.focus = [
        FocusStop("1", True),
        FocusStop("2", False),
        FocusStop("3", True, obscured_by="#cookie-banner"),
    ]
    assert [s for s, _ in found(page, "RL804")] == ["#e2"]
    assert found(page, "RL805")[0][1].startswith(
        "When focused, the element is completely hidden behind #cookie-banner"
    )
    page.focus = None
    assert found(page, "RL804") == []


def test_keyboard_trap():
    page = snapshot(*[("button", "", (0, 0, 40, 40), {})] * 2, keyboard_trap=("1", "2"))
    assert found(page, "RL806") == [
        (
            "#e1",
            "Keyboard trap: Tab moves between 2 elements and never leaves them (WCAG 2.1.2); "
            "let Tab and Shift+Tab move on",
        )
    ]


def state_page(*elements) -> PageSnapshot:
    page = snapshot(*elements)
    for info in page.elements.values():
        info.selector = f"#s{info.id}"
    return page


def test_dialog_focus_and_expanded_state():
    page = snapshot(("button", 'aria-expanded="false"', (0, 0, 40, 40), {}))
    opened = state_page(("div", 'role="dialog" aria-modal="true"', (0, 0, 200, 200), {}))
    page.states = [
        UiState(
            'after clicking "Help" (#e1)', "#e1", opened, ("1",), None, Dialog("#s1", False, True)
        ),
        UiState(
            'after clicking "Ok" (#e1)', "#e1", opened, ("1",), None, Dialog("#s1", True, True)
        ),
        UiState(
            'after clicking "Fine" (#e1)', "#e1", opened, ("1",), None, Dialog("#s1", True, False)
        ),
        UiState('after clicking "More" (#s1)', "#s1", opened, ("1",), False),
        UiState('after clicking "Same" (#s1)', "#s1", opened, (), False),  # nothing opened
        UiState('after clicking "Good" (#s1)', "#s1", opened, ("1",), True),
    ]
    result = check_page(page, select_rules(["RL806", "RL807"]))
    assert [(v.code, v.state, v.message[:30]) for v in result.violations] == [
        ("RL806", 'after clicking "Help" (#e1)', "The dialog opens without movin"),
        ("RL806", 'after clicking "Ok" (#e1)', "Tab moves focus out of the ope"),
        ("RL807", 'after clicking "More" (#s1)', 'aria-expanded stays "false" af'),
    ]
    assert all(v.selector == "#s1" and v.url == URL for v in result.violations)


def test_state_markup_is_checked_only_where_it_changed():
    page = snapshot(("img", 'src="a.png" alt="ok"', (0, 0, 10, 10), {}))
    opened = state_page(
        ("img", 'src="old.png"', (0, 0, 10, 10), {}),  # was there before: not reported again
        ("img", 'src="new.png"', (0, 0, 10, 10), {}),
    )
    opened.texts = [text("2", "rgb(200, 200, 200)", "rgb(255, 255, 255)")]
    page.states = [UiState('after clicking "Menu" (#m)', "#m", opened, ("2",))]
    result = check_page(page, select_rules(["RL101", "RL801"]))
    assert [(v.code, v.selector, v.state) for v in result.violations] == [
        ("RL101", "#s2", 'after clicking "Menu" (#m)'),
        ("RL801", "#s2", 'after clicking "Menu" (#m)'),
    ]


@pytest.mark.parametrize("code", ["RL801", "RL802", "RL803", "RL804", "RL805", "RL806", "RL807"])
def test_every_rendered_rule_is_browser_only(code):
    (rule,) = select_rules([code])
    assert rule.browser_only and rule.page_check is not None
