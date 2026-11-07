"""Probes: things a static snapshot cannot show, found by using the page.

Each probe runs on the loaded page after the snapshot was taken and adds to it:

* :func:`focus_order` presses Tab through the page and records, for every
  stop, whether focus is visible and whether a sticky header hides it;
* :func:`reflow` narrows the viewport to 320 CSS px and measures what sticks out;
* :func:`ui_states` clicks menus, dialogs, tabs and ``<details>`` one by one and
  snapshots what appears. While it does, the page cannot navigate away, open
  windows or send anything but GET requests.
"""

from __future__ import annotations

import contextlib
import re
import time
from collections.abc import Iterable
from importlib.resources import files
from typing import TYPE_CHECKING, Any

from ramplint.browser.options import BrowserOptions
from ramplint.browser.snapshot import Dialog, FocusStop, PageSnapshot, Reflow, UiState

if TYPE_CHECKING:
    from ramplint.browser.session import BrowserSession, Probe
    from ramplint.rules import Rule

PROBES_JS = files("ramplint.browser").joinpath("probes.js").read_text(encoding="utf-8")

#: Tab presses per page; the focus rules share one walk.
MAX_TAB_STOPS = 200
#: A Tab walk that stays among this few elements for TRAP_WINDOW presses is a trap.
TRAP_SIZE = 3
TRAP_WINDOW = 12
#: WCAG 1.4.10: content must work at 320 CSS px without horizontal scrolling.
REFLOW_WIDTH = 320
#: The DOM is settled after this long without mutations (at most SETTLE_MAX_MS).
SETTLE_QUIET_MS = 150
SETTLE_MAX_MS = 1500
CLICK_TIMEOUT_MS = 2000
#: Presses of Tab inside an open dialog to see whether focus stays in it.
DIALOG_TABS = 6
_MARK_RE = re.compile(r' data-rl-before="[01]"')

FOCUS_RULES = frozenset({"RL804", "RL805", "RL806"})
REFLOW_RULES = frozenset({"RL803"})


def _install(page: Any) -> None:
    page.evaluate(PROBES_JS)


def _call(page: Any, function: str, *args: Any) -> Any:
    return page.evaluate(f"(args) => window.__ramplint.{function}(...args)", list(args))


# -- focus ------------------------------------------------------------------------


def _pixels_differ(session: BrowserSession, page: Any, node: str, rect: list[float]) -> bool:
    """Compare the element focused and unfocused, pixel for pixel (PNG bytes)."""
    x, y, width, height = rect
    clip = {"x": max(x - 4, 0), "y": max(y - 4, 0), "width": width + 8, "height": height + 8}
    if clip["width"] <= 0 or clip["height"] <= 0:
        return False
    focused = page.screenshot(type="png", clip=clip, animations="disabled")
    page.evaluate(f"() => document.querySelector('[data-rl-node=\"{node}\"]')?.blur()")
    unfocused = page.screenshot(type="png", clip=clip, animations="disabled")
    page.evaluate(
        f"() => document.querySelector('[data-rl-node=\"{node}\"]')?.focus({{preventScroll: true}})"
    )
    return focused != unfocused


def focus_order(
    session: BrowserSession, page: Any, snapshot: PageSnapshot, deadline: float
) -> None:
    """Tab through the page (RL804 focus-visible, RL805 focus-obscured, RL806 traps)."""
    _install(page)
    page.evaluate("() => { document.activeElement?.blur(); window.scrollTo(0, 0); }")
    total = _call(page, "focusableCount")
    stops: list[FocusStop] = []
    sequence: list[str] = []
    for _ in range(min(MAX_TAB_STOPS, total + TRAP_WINDOW)):
        if time.monotonic() >= deadline:
            break
        page.keyboard.press("Tab")
        info = _call(page, "focused")
        if info is None:
            if stops:
                break  # focus left the page: the walk is complete
            continue
        node = info["id"]
        if node is None:
            continue  # added after the snapshot; nothing to report it against
        if sequence and node == sequence[0] and len(sequence) > 1:
            break  # back at the start
        sequence.append(node)
        trap = _trap(sequence, total)
        if trap:
            snapshot.keyboard_trap = trap
            break
        if node in {stop.element for stop in stops}:
            continue
        unfocused = _call(page, "blurActive")
        page.evaluate(
            f"() => document.querySelector('[data-rl-node=\"{node}\"]')"
            "?.focus({preventScroll: true})"
        )
        indicator = unfocused != info["signature"] or _pixels_differ(
            session, page, node, info["rect"]
        )
        stops.append(FocusStop(node, indicator, info["obscuredBy"]))
    snapshot.focus = stops


def _trap(sequence: list[str], focusable: int) -> tuple[str, ...]:
    """The elements of a keyboard trap at the end of ``sequence``, or ``()``.

    Tab keeps coming back to the same few elements while the page has more:
    the elements that repeat in the last presses are the trap (the one focus
    came from on the way in is not part of it).
    """
    if len(sequence) < TRAP_WINDOW:
        return ()
    window = sequence[-TRAP_WINDOW:]
    repeating = [node for node in dict.fromkeys(window) if window.count(node) > 1]
    if repeating and len(set(window)) <= TRAP_SIZE and focusable > len(repeating) + 1:
        return tuple(repeating)
    return ()


# -- reflow -----------------------------------------------------------------------


def reflow(session: BrowserSession, page: Any, snapshot: PageSnapshot, deadline: float) -> None:
    """Measure the page at 320 CSS px (RL803)."""
    _install(page)
    size = page.viewport_size
    if size is not None and size["width"] != REFLOW_WIDTH:
        page.set_viewport_size({"width": REFLOW_WIDTH, "height": 640})
    try:
        _call(page, "settle", SETTLE_QUIET_MS, SETTLE_MAX_MS)
        data = _call(page, "reflow")
        snapshot.reflow = Reflow(
            width=int(data["width"]),
            scroll_width=int(data["scrollWidth"]),
            offenders=tuple((selector, float(right)) for selector, right in data["offenders"]),
        )
    finally:
        if size is not None:
            page.set_viewport_size(size)


# -- menus, dialogs, tabs ---------------------------------------------------------


class _Guard:
    """Blocks navigation and every non-GET request of a page while it is active."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.blocked: list[str] = []
        self.allow_navigation = False

    def __enter__(self) -> _Guard:
        self.page.route("**/*", self._handle)
        return self

    def __exit__(self, *exc: object) -> None:
        with contextlib.suppress(Exception):
            self.page.unroute("**/*", self._handle)

    def _handle(self, route: Any) -> None:
        request = route.request
        navigation = request.is_navigation_request() and request.frame == self.page.main_frame
        if request.method != "GET" or (navigation and not self.allow_navigation):
            self.blocked.append(f"{request.method} {request.url}")
            route.abort()
        else:
            route.continue_()


def ui_states(session: BrowserSession, page: Any, snapshot: PageSnapshot, deadline: float) -> None:
    """Click each trigger on a fresh page and snapshot what it opens (states, RL806)."""
    _install(page)
    triggers = _call(page, "triggers", session.options.max_states)
    if not triggers:
        return
    with _Guard(page) as guard:
        for index, trigger in enumerate(triggers):
            if time.monotonic() >= deadline:
                break
            if index:
                guard.allow_navigation = True
                left = max(deadline - time.monotonic(), 1.0)
                try:
                    page.reload(wait_until="load", timeout=1000 * left)
                finally:
                    guard.allow_navigation = False
                _install(page)
            state = _open_state(session, page, snapshot, trigger, guard)
            if state is not None:
                snapshot.states.append(state)


def _open_state(
    session: BrowserSession,
    page: Any,
    snapshot: PageSnapshot,
    trigger: dict[str, Any],
    guard: _Guard,
) -> UiState | None:
    from playwright.sync_api import Error as PlaywrightError

    page.evaluate("() => window.__ramplint.guard()")
    _call(page, "markBefore")
    selector = trigger["selector"]
    blocked_before = len(guard.blocked)
    try:
        page.locator(selector).first.click(timeout=CLICK_TIMEOUT_MS, no_wait_after=True)
    except PlaywrightError:
        return None  # covered, detached or not clickable: not a state we can reach
    _call(page, "settle", SETTLE_QUIET_MS, SETTLE_MAX_MS)

    state_page = PageSnapshot(
        url=snapshot.url,
        viewport=snapshot.viewport,
        final_url=snapshot.final_url,
        status=snapshot.status,
        content_type=snapshot.content_type,
    )
    session.collect(page, state_page, full_page=False)
    changed = tuple(_call(page, "changed"))
    state_page.html = _MARK_RE.sub("", state_page.html)

    expanded = None
    if trigger["expanded"] is False:
        expanded = _call(page, "expandedOf", selector)
    dialog = _dialog(page)
    label = trigger["label"] or trigger["tag"]
    return UiState(
        description=f'after clicking "{label}" ({selector})',
        trigger=selector,
        page=state_page,
        changed=changed,
        expanded=expanded,
        dialog=dialog,
        blocked=tuple(guard.blocked[blocked_before:]),
    )


def _dialog(page: Any) -> Dialog | None:
    found = _call(page, "modalDialog")
    if found is None:
        return None
    escapes = False
    for _ in range(DIALOG_TABS):
        page.keyboard.press("Tab")
        if not _call(page, "focusInside", found["selector"]):
            escapes = True
            break
    return Dialog(found["selector"], bool(found["focusInside"]), escapes)


def probes_for(rules: Iterable[Rule], options: BrowserOptions) -> list[Probe]:
    """The probes the selected rules and the options need, in the order they run."""
    codes = {rule.code for rule in rules}
    probes: list[Probe] = []
    if codes & FOCUS_RULES:
        probes.append(focus_order)
    if codes & REFLOW_RULES:
        probes.append(reflow)
    if options.max_states > 0:
        probes.append(ui_states)
    return probes
