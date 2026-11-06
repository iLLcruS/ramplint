"""The only module that talks to the browser (Playwright + Chromium)."""

from __future__ import annotations

import contextlib
import json
import time
from importlib.resources import files
from types import TracebackType
from typing import Any

from ramplint.browser.options import BrowserOptions, Viewport
from ramplint.browser.snapshot import ElementInfo, PageSnapshot

INSTALL_HINT = 'pip install "ramplint[browser]" && playwright install chromium'

COLLECT_JS = files("ramplint.browser").joinpath("collect.js").read_text(encoding="utf-8")
#: Network idle is a nice-to-have: pages that poll never reach it.
NETWORK_IDLE_TIMEOUT = 5.0
JPEG_QUALITY = 70


class BrowserUnavailable(Exception):
    """Playwright or Chromium is not installed (or Chromium cannot start)."""


def _first_line(message: str) -> str:
    """The useful part of a Playwright error (``net::ERR_CONNECTION_REFUSED at ...``)."""
    for line in str(message).splitlines():
        line = line.strip()
        if line and not line.startswith("="):
            return line.removeprefix("Page.goto: ")
    return str(message).strip()


class BrowserSession:
    """Chromium with one browser context per viewport.

    Use as a context manager::

        with BrowserSession(options) as session:
            snapshot = session.capture("http://localhost:8000/", options.viewports[0])
    """

    def __init__(self, options: BrowserOptions) -> None:
        self.options = options
        self._playwright: Any = None
        self._browser: Any = None
        self._contexts: dict[Viewport, Any] = {}

    # -- lifecycle -----------------------------------------------------------
    def __enter__(self) -> BrowserSession:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailable(
                f"the browser mode needs Playwright. Install it with: {INSTALL_HINT}"
            ) from exc
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=not self.options.headed)
        except Exception as exc:
            self._playwright.stop()
            message = _first_line(str(exc))
            if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                message = "Chromium is not installed. Install it with: playwright install chromium"
            raise BrowserUnavailable(message) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        # Closing may fail when the browser is already gone; nothing to do then.
        for context in self._contexts.values():
            with contextlib.suppress(Exception):
                context.close()
        self._contexts.clear()
        if self._browser is not None:
            with contextlib.suppress(Exception):
                self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _context(self, viewport: Viewport) -> Any:
        if viewport not in self._contexts:
            self._contexts[viewport] = self._browser.new_context(
                viewport={"width": viewport.width, "height": viewport.height},
                is_mobile=viewport.mobile,
                has_touch=viewport.mobile,
                device_scale_factor=1,
                reduced_motion="reduce",
                ignore_https_errors=True,
            )
        return self._contexts[viewport]

    # -- capturing -----------------------------------------------------------
    def capture(self, url: str, viewport: Viewport) -> PageSnapshot:
        """Open ``url`` and capture everything checks and reports need.

        Never raises for problems with the page itself (network errors,
        timeouts): they end up in :attr:`PageSnapshot.error`.
        """
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        snapshot = PageSnapshot(url=url, viewport=viewport.name, final_url=url)
        timeout = self.options.timeout
        deadline = time.monotonic() + timeout
        page = self._context(viewport).new_page()
        page.on(
            "console",
            lambda message: (
                snapshot.console_errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.on("pageerror", lambda error: snapshot.console_errors.append(str(error)))

        def remaining_ms(cap: float | None = None) -> float:
            left = max(deadline - time.monotonic(), 0.1)
            return 1000 * (min(left, cap) if cap is not None else left)

        try:
            try:
                response = page.goto(url, wait_until="load", timeout=remaining_ms())
            except PlaywrightTimeout:
                snapshot.error = f"timed out after {timeout:g}s"
                return snapshot
            except PlaywrightError as exc:
                snapshot.error = _first_line(exc.message)
                return snapshot

            snapshot.final_url = page.url
            if response is not None:
                snapshot.status = response.status
                snapshot.content_type = response.headers.get("content-type", "")
            if not snapshot.is_html:
                return snapshot

            with contextlib.suppress(PlaywrightTimeout):
                page.wait_for_load_state("networkidle", timeout=remaining_ms(NETWORK_IDLE_TIMEOUT))
            if self.options.wait_for:
                try:
                    page.wait_for_selector(
                        self.options.wait_for, state="attached", timeout=remaining_ms()
                    )
                except PlaywrightTimeout:
                    snapshot.error = f"{self.options.wait_for!r} did not appear in {timeout:g}s"
                    return snapshot

            self._collect(page, snapshot)
        finally:
            page.close()
        return snapshot

    def _collect(self, page: Any, snapshot: PageSnapshot) -> None:
        data = json.loads(page.evaluate(COLLECT_JS))
        snapshot.title = data["title"]
        snapshot.page_size = (int(data["page"][0]), int(data["page"][1]))
        for raw in data["elements"]:
            snapshot.elements[raw["id"]] = ElementInfo(
                id=raw["id"],
                tag=raw["tag"],
                selector=raw["selector"],
                box=tuple(round(v, 1) for v in raw["box"]),  # type: ignore[arg-type]
                visible=bool(raw["visible"]),
                styles=raw["styles"],
            )
        self._accessibility_tree(page, snapshot)
        snapshot.html = page.content()
        snapshot.screenshot = page.screenshot(type="jpeg", quality=JPEG_QUALITY)
        snapshot.full_screenshot = page.screenshot(
            type="jpeg", quality=JPEG_QUALITY, full_page=True
        )

    @staticmethod
    def _accessibility_tree(page: Any, snapshot: PageSnapshot) -> None:
        """Role and accessible name of every element, as Chromium computes them."""
        try:
            cdp = page.context.new_cdp_session(page)
            document = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
            ax_tree = cdp.send("Accessibility.getFullAXTree")
            cdp.detach()
        except Exception:  # pragma: no cover - CDP is part of every Chromium
            return

        backend_to_id: dict[int, str] = {}
        stack = [document["root"]]
        while stack:
            node = stack.pop()
            attributes = node.get("attributes") or []
            for index in range(0, len(attributes) - 1, 2):
                if attributes[index] == "data-rl-node":
                    backend_to_id[node["backendNodeId"]] = attributes[index + 1]
                    break
            stack.extend(node.get("children") or [])
            stack.extend(node.get("shadowRoots") or [])

        for ax_node in ax_tree.get("nodes", []):
            element = snapshot.element(backend_to_id.get(ax_node.get("backendDOMNodeId", -1)))
            if element is None:
                continue
            element.ax_ignored = bool(ax_node.get("ignored"))
            element.role = (ax_node.get("role") or {}).get("value") or None
            name = (ax_node.get("name") or {}).get("value")
            element.name = name if isinstance(name, str) else None
