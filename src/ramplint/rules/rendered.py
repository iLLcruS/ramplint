"""Rules that need a rendered page (browser mode): RL801-RL807.

They read what only a browser knows: computed colours, element boxes, the
focus order and what menus and dialogs do when they open. In template mode
they are skipped.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import TYPE_CHECKING

from ramplint.browser.color import composite, contrast_ratio, is_large_text, parse_color
from ramplint.rules.base import Finding, page_rule

if TYPE_CHECKING:
    from ramplint.browser.snapshot import Box, ElementInfo, PageSnapshot
    from ramplint.dom import Node

#: WCAG 2.5.8: targets of at least 24 by 24 CSS px, or 24 px apart.
TARGET_SIZE = 24.0
_INTERACTIVE_TAGS = frozenset({"button", "select", "textarea", "summary"})
_INTERACTIVE_ROLES = frozenset(
    {
        "button", "link", "checkbox", "radio", "switch", "tab", "menuitem",
        "menuitemcheckbox", "menuitemradio", "option", "slider", "spinbutton",
    }
)  # fmt: skip
_TEXT_BLOCKS = frozenset({"p", "li", "td", "th", "dd", "dt", "label", "span", "figcaption"})


# -- RL801 color-contrast ----------------------------------------------------------


@page_rule(
    "RL801",
    "color-contrast",
    "Text must have a contrast of at least 4.5:1 (3:1 for large text).",
    "1.4.3 Contrast (Minimum) (AA)",
    on_states=True,
)
def color_contrast(page: PageSnapshot) -> Iterator[Finding]:
    for sample in page.texts:
        element = page.element(sample.element)
        if element is None or not element.visible or sample.opacity <= 0:
            continue
        if _disabled(page, sample.element):
            continue  # WCAG exempts inactive controls
        foreground = parse_color(sample.color)
        backgrounds = [parse_color(color) for color in sample.backgrounds]
        if sample.over_image or foreground is None or None in backgrounds:
            yield Finding(
                sample.element,
                "Text over a background image or gradient (or in a colour format ramplint "
                "cannot read): check its contrast by hand",
                manual=True,
            )
            continue
        background = composite([c for c in backgrounds if c is not None])
        ratio = contrast_ratio(foreground.with_alpha(sample.opacity), background)
        large = is_large_text(sample.font_size, sample.font_weight)
        needed = 3.0 if large else 4.5
        if ratio < needed:
            kind = "large text" if large else "text"
            text = foreground.with_alpha(sample.opacity).over(background)
            yield Finding(
                sample.element,
                f"Contrast of {ratio:.2f}:1 is below {needed:g}:1 for {kind} "
                f"({text.hex} on {background.hex}); darken the text or lighten the background",
            )


def _disabled(page: PageSnapshot, element: str) -> bool:
    node = page.tree.nodes.get(element)
    while node is not None:
        if "disabled" in node.attrs or node.get("aria-disabled") == "true":
            return True
        node = node.parent
    return False


# -- RL802 target-size -------------------------------------------------------------


def _is_target(node: Node) -> bool:
    if node.tag == "a" and "href" in node.attrs:
        return True
    if node.tag == "input":
        return (node.get("type") or "text").lower() != "hidden"
    return node.tag in _INTERACTIVE_TAGS or (node.get("role") or "") in _INTERACTIVE_ROLES


def _inline_in_text(node: Node, element: ElementInfo) -> bool:
    """A link inside a sentence: WCAG exempts it from the size requirement."""
    if element.styles.get("display", "inline") != "inline" or node.parent is None:
        return False
    parent = node.parent
    own_text = "".join(child for child in parent.children if isinstance(child, str))
    return (
        bool(own_text.strip())
        or parent.tag in _TEXT_BLOCKS
        and len(parent.text()) > len(node.text())
    )


#: Chromium's default font size and border styles of form controls. A control
#: that keeps both was not restyled by the author, and WCAG exempts targets
#: whose size the user agent determines.
_UA_CONTROL_FONT_SIZE = "13.3333px"
_UA_CONTROL_BORDERS = frozenset({"outset", "inset"})
_NATIVE_CONTROLS = frozenset({"button", "input", "select", "textarea"})


def _browser_default_control(node: Node, element: ElementInfo) -> bool:
    styles = element.styles
    if node.tag not in _NATIVE_CONTROLS or styles.get("font-size") != _UA_CONTROL_FONT_SIZE:
        return False
    return node.tag == "select" or styles.get("border-top-style") in _UA_CONTROL_BORDERS


def _labelled_native_choice(page: PageSnapshot, node: Node) -> bool:
    """Native checkboxes and radios are small; their label is the real target."""
    if node.tag != "input" or (node.get("type") or "").lower() not in ("checkbox", "radio"):
        return False
    if any(ancestor.tag == "label" for ancestor in node.ancestors()):
        return True
    control_id = node.get("id")
    return bool(control_id) and any(
        label.get("for") == control_id for label in page.tree.root.iter("label")
    )


def _center(box: Box) -> tuple[float, float]:
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def _circle_hits_box(center: tuple[float, float], radius: float, box: Box) -> bool:
    x, y = center
    nearest_x = min(max(x, box[0]), box[0] + box[2])
    nearest_y = min(max(y, box[1]), box[1] + box[3])
    return math.hypot(x - nearest_x, y - nearest_y) < radius


@page_rule(
    "RL802",
    "target-size",
    "Clickable targets must be at least 24 by 24 CSS pixels, or have room around them.",
    "2.5.8 Target Size (Minimum) (AA)",
    on_states=True,
)
def target_size(page: PageSnapshot) -> Iterator[Finding]:
    targets: list[tuple[str, Node, ElementInfo]] = []
    for node_id, node in page.tree.nodes.items():
        element = page.element(node_id)
        if element is None or not element.visible or not _is_target(node):
            continue
        if element.box[2] <= 0 or element.box[3] <= 0:
            continue
        targets.append((node_id, node, element))
    small = {
        node_id
        for node_id, node, element in targets
        if min(element.box[2], element.box[3]) < TARGET_SIZE - 0.5
        and not _inline_in_text(node, element)
        and not _labelled_native_choice(page, node)
        and not _browser_default_control(node, element)
    }
    radius = TARGET_SIZE / 2
    for node_id, _node, element in targets:
        if node_id not in small:
            continue
        center = _center(element.box)
        crowded = False
        for other_id, _other, other in targets:
            if other_id == node_id:
                continue
            if other_id in small:
                crowded = math.dist(center, _center(other.box)) < TARGET_SIZE
            else:
                crowded = _circle_hits_box(center, radius, other.box)
            if crowded:
                break
        if crowded:
            yield Finding(
                node_id,
                "Target is smaller than 24x24 px and too close to another target; make it at "
                "least 24x24 px or leave 24 px between targets",
            )


# -- RL803 reflow ------------------------------------------------------------------


@page_rule(
    "RL803",
    "reflow",
    "Content must fit a 320 CSS pixel wide screen without scrolling sideways.",
    "1.4.10 Reflow (AA)",
)
def reflow(page: PageSnapshot) -> Iterator[Finding]:
    result = page.reflow
    if result is None or not result.scrolls or not result.offenders:
        return
    selector, right = result.offenders[0]
    element = page.by_selector(selector)
    yield Finding(
        element.id if element else None,
        f"At {result.width} px wide the page scrolls sideways ({result.scroll_width} px of "
        f"content): {selector} ends at {right:.0f} px; let it wrap or shrink (max-width: 100%)",
    )


# -- RL804-RL806 focus ---------------------------------------------------------------


@page_rule(
    "RL804",
    "focus-visible",
    "Keyboard focus must be visible.",
    "2.4.7 Focus Visible (AA)",
)
def focus_visible(page: PageSnapshot) -> Iterator[Finding]:
    for stop in page.focus or ():
        if stop.indicator is False:
            yield Finding(
                stop.element,
                "Focus is not visible: the element looks the same with and without "
                "keyboard focus; add a :focus-visible style (e.g. an outline)",
            )


@page_rule(
    "RL805",
    "focus-obscured",
    "A focused element must not be hidden behind sticky or fixed content.",
    "2.4.11 Focus Not Obscured (Minimum) (AA)",
)
def focus_obscured(page: PageSnapshot) -> Iterator[Finding]:
    for stop in page.focus or ():
        if stop.obscured_by:
            yield Finding(
                stop.element,
                f"When focused, the element is completely hidden behind {stop.obscured_by}; "
                "add scroll-padding to the page or keep the banner from covering content",
            )


@page_rule(
    "RL806",
    "dialog-focus",
    "Modal dialogs must take focus and keep it; Tab must never get stuck.",
    "2.4.3 Focus Order (A), 2.1.2 No Keyboard Trap (A)",
)
def dialog_focus(page: PageSnapshot) -> Iterator[Finding]:
    if page.keyboard_trap:
        yield Finding(
            page.keyboard_trap[0],
            f"Keyboard trap: Tab moves between {len(page.keyboard_trap)} elements and never "
            "leaves them (WCAG 2.1.2); let Tab and Shift+Tab move on",
        )
    for index, state in enumerate(page.states):
        dialog = state.dialog
        if dialog is None:
            continue
        element = state.page.by_selector(dialog.selector)
        node = element.id if element else None
        if not dialog.focus_inside:
            yield Finding(
                node,
                "The dialog opens without moving focus into it; focus its first control "
                "(or the dialog) when it opens",
                state=index,
            )
        elif dialog.tab_escapes:
            yield Finding(
                node,
                "Tab moves focus out of the open modal dialog; keep focus inside until it "
                "closes (a <dialog> opened with showModal() does this)",
                state=index,
            )


# -- RL807 expanded-state -------------------------------------------------------------


@page_rule(
    "RL807",
    "expanded-state",
    'A control that opens content must set aria-expanded="true" when it does.',
    "4.1.2 Name, Role, Value (A)",
)
def expanded_state(page: PageSnapshot) -> Iterator[Finding]:
    for index, state in enumerate(page.states):
        if state.expanded is False and state.changed:
            element = state.page.by_selector(state.trigger)
            yield Finding(
                element.id if element else None,
                'aria-expanded stays "false" after the control opened content; set it to '
                '"true" while the content is shown',
                state=index,
            )
