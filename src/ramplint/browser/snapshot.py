"""What ramplint knows about one rendered page in one viewport.

A :class:`PageSnapshot` is captured once by :mod:`ramplint.browser.session`
(and the probes in :mod:`ramplint.browser.probes`); checks and reports only
read it. ``save()`` / ``load()`` keep it on disk, which is how the tests check
rules without starting a browser.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from functools import cached_property
from pathlib import Path
from typing import Any

from ramplint import dom
from ramplint.template import Suppressions, prepare

SNAPSHOT_SCHEMA = 2

#: ``(x, y, width, height)`` in CSS pixels, relative to the top of the page.
Box = tuple[float, float, float, float]

#: Files of the two screenshots, without the extension.
_SCREENSHOTS = (("screenshot", "screenshot"), ("full", "full_screenshot"))


def image_extension(data: bytes) -> str:
    """``png`` or ``jpg``, from the first bytes of the image."""
    return "png" if data.startswith(b"\x89PNG") else "jpg"


def padded_box(box: Box, padding: float, size: tuple[int, int]) -> Box | None:
    """``box`` grown by ``padding`` on every side and clipped to a page of ``size``.

    ``None`` when nothing of the element is on the page (hidden, zero size or
    outside of it).
    """
    x, y, width, height = box
    if width <= 0 or height <= 0:
        return None
    left = max(x - padding, 0.0)
    top = max(y - padding, 0.0)
    right = min(x + width + padding, float(size[0]))
    bottom = min(y + height + padding, float(size[1]))
    if right <= left or bottom <= top:
        return None
    return (left, top, right - left, bottom - top)


#: Fields stored as JSON lists that are tuples in the dataclasses.
_TUPLE_FIELDS = frozenset({"box", "backgrounds"})


def _build(cls: type, raw: dict[str, Any]) -> Any:
    """A dataclass from its ``asdict()`` form (tuples come back from JSON lists)."""
    values = {k: tuple(v) if k in _TUPLE_FIELDS else v for k, v in raw.items()}
    return cls(**values)


#: Attribute ramplint gives every element of a page it captures.
NODE_ATTRIBUTE = "data-rl-node"


@dataclass(frozen=True)
class PageTree:
    root: dom.Node
    nodes: dict[str, dom.Node]


@dataclass
class ElementInfo:
    #: Value of the ``data-rl-node`` attribute ramplint gave the element.
    id: str
    tag: str
    selector: str
    box: Box
    #: Rendered: not ``display: none``, not ``visibility: hidden``, has a box.
    visible: bool
    styles: dict[str, str] = field(default_factory=dict)
    #: Role and accessible name computed by the browser (accessibility tree).
    role: str | None = None
    name: str | None = None
    #: The browser leaves the element out of the accessibility tree.
    ax_ignored: bool = False
    #: ``template.html:line:col`` that produced the element (Django source map).
    source: str | None = None


@dataclass
class NetworkRecord:
    """An XHR or ``fetch`` request a page made while it loaded."""

    method: str
    url: str
    status: int | None = None
    content_type: str = ""
    #: Response size in bytes (from ``Content-Length``), when known.
    size: int | None = None
    #: ``xhr`` or ``fetch``.
    kind: str = "fetch"

    @property
    def is_html(self) -> bool:
        return self.content_type.split(";")[0].strip().lower() == "text/html"


@dataclass
class TextSample:
    """Colours of an element with its own text, for the contrast check."""

    element: str
    #: Computed ``color`` (``rgb()`` / ``rgba()``).
    color: str
    #: Background colours from the element up to the first opaque one.
    backgrounds: tuple[str, ...]
    #: A background image or gradient lies behind the text.
    over_image: bool
    font_size: float
    font_weight: int
    #: Opacity of the element and its ancestors, multiplied.
    opacity: float = 1.0


@dataclass
class FocusStop:
    """One Tab stop: what had focus and how it looked."""

    element: str
    #: The focused element looks different from the unfocused one
    #: (``None`` when it could not be compared).
    indicator: bool | None
    #: Selector of a fixed or sticky element that hides the focused element.
    obscured_by: str | None = None


@dataclass
class Reflow:
    """The page at a narrow viewport (320 CSS px, WCAG reflow)."""

    width: int
    scroll_width: int
    #: ``(selector, right edge)`` of the elements that stick out the most.
    offenders: tuple[tuple[str, float], ...] = ()

    @property
    def scrolls(self) -> bool:
        return self.scroll_width > self.width + 1


@dataclass
class Dialog:
    """A modal dialog opened by a trigger."""

    selector: str
    #: Focus moved into the dialog when it opened.
    focus_inside: bool
    #: Pressing Tab moved focus out of the open dialog.
    tab_escapes: bool


@dataclass
class UiState:
    """The page after clicking a trigger (menu, dialog, tab, details)."""

    #: ``after clicking "Menu" (button#nav-toggle)``.
    description: str
    trigger: str
    page: PageSnapshot
    #: Elements that appeared or became visible (``data-rl-node`` values).
    changed: tuple[str, ...] = ()
    #: ``aria-expanded`` was ``false`` before; ``True`` when it became ``true``.
    expanded: bool | None = None
    dialog: Dialog | None = None
    #: Requests that were blocked while the trigger was clicked (non-GET, navigation).
    blocked: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "trigger": self.trigger,
            "page": self.page.to_dict(include_html=True),
            "changed": list(self.changed),
            "expanded": self.expanded,
            "dialog": asdict(self.dialog) if self.dialog else None,
            "blocked": list(self.blocked),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UiState:
        return cls(
            description=data["description"],
            trigger=data["trigger"],
            page=PageSnapshot.from_dict(data["page"]),
            changed=tuple(data.get("changed", ())),
            expanded=data.get("expanded"),
            dialog=Dialog(**data["dialog"]) if data.get("dialog") else None,
            blocked=tuple(data.get("blocked", ())),
        )


@dataclass
class PageSnapshot:
    url: str
    viewport: str
    #: URL after redirects.
    final_url: str = ""
    status: int | None = None
    content_type: str = ""
    title: str = ""
    #: Rendered HTML (``document.documentElement.outerHTML``) with ``data-rl-node``.
    html: str = ""
    elements: dict[str, ElementInfo] = field(default_factory=dict)
    #: Size of the whole page in CSS pixels.
    page_size: tuple[int, int] = (0, 0)
    console_errors: list[str] = field(default_factory=list)
    #: XHR and ``fetch`` requests made while the page loaded.
    requests: list[NetworkRecord] = field(default_factory=list)
    #: URLs the page redirected through before ``final_url``.
    redirects: list[str] = field(default_factory=list)
    #: Elements with their own text and their colours (contrast).
    texts: list[TextSample] = field(default_factory=list)
    #: The Tab order, when the keyboard was probed (``None`` when it was not).
    focus: list[FocusStop] | None = None
    #: Elements Tab could not leave (a keyboard trap), when found.
    keyboard_trap: tuple[str, ...] = ()
    reflow: Reflow | None = None
    states: list[UiState] = field(default_factory=list)
    #: Why the page could not be loaded (network error, timeout); empty when it loaded.
    error: str = ""
    screenshot: bytes | None = field(default=None, repr=False)
    full_screenshot: bytes | None = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def is_html(self) -> bool:
        kind = self.content_type.split(";")[0].strip().lower()
        return self.ok and kind in ("", "text/html", "application/xhtml+xml")

    def element(self, node_id: str | None) -> ElementInfo | None:
        return self.elements.get(node_id) if node_id is not None else None

    @cached_property
    def suppressions(self) -> Suppressions:
        """``<!-- ramplint: ignore ... -->`` comments, which survive rendering."""
        return prepare(self.html).suppressions

    @cached_property
    def tree(self) -> PageTree:
        """The rendered HTML parsed once, with its elements by ``data-rl-node``."""
        root = dom.parse(self.html)
        nodes = {n.attrs[NODE_ATTRIBUTE]: n for n in root.iter() if NODE_ATTRIBUTE in n.attrs}
        return PageTree(root, nodes)

    def by_selector(self, selector: str) -> ElementInfo | None:
        return next((e for e in self.elements.values() if e.selector == selector), None)

    # -- persistence -------------------------------------------------------
    def to_dict(self, include_html: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for item in fields(self):
            if item.name in ("screenshot", "full_screenshot", "states", "elements"):
                continue
            value = getattr(self, item.name)
            data[item.name] = asdict(value) if hasattr(value, "__dataclass_fields__") else value
        data["requests"] = [asdict(r) for r in self.requests]
        data["texts"] = [asdict(t) for t in self.texts]
        data["focus"] = [asdict(f) for f in self.focus] if self.focus is not None else None
        data["elements"] = [asdict(e) for e in self.elements.values()]
        data["states"] = [state.to_dict() for state in self.states]
        if not include_html:
            data.pop("html")
        return {"schema": SNAPSHOT_SCHEMA, **data}

    @classmethod
    def from_dict(cls, data: dict[str, Any], html: str | None = None) -> PageSnapshot:
        data = dict(data)
        if data.pop("schema", SNAPSHOT_SCHEMA) != SNAPSHOT_SCHEMA:
            raise ValueError("unsupported snapshot schema")
        elements = {}
        for raw in data.pop("elements", []):
            element = _build(ElementInfo, raw)
            elements[element.id] = element
        data["page_size"] = tuple(data.get("page_size", (0, 0)))
        data["requests"] = [NetworkRecord(**r) for r in data.get("requests", [])]
        data["texts"] = [_build(TextSample, t) for t in data.get("texts", [])]
        focus = data.get("focus")
        data["focus"] = [FocusStop(**f) for f in focus] if focus is not None else None
        data["keyboard_trap"] = tuple(data.get("keyboard_trap", ()))
        reflow = data.get("reflow")
        if reflow:
            offenders = tuple(tuple(o) for o in reflow.get("offenders", ()))
            data["reflow"] = Reflow(reflow["width"], reflow["scroll_width"], offenders)
        data["states"] = [UiState.from_dict(s) for s in data.get("states", [])]
        if html is not None:
            data["html"] = html
        return cls(**data, elements=elements)

    def save(self, folder: str | Path) -> Path:
        """Write the snapshot to ``folder`` (created if needed) and return it."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "snapshot.json").write_text(
            json.dumps(self.to_dict(), indent=1), encoding="utf-8"
        )
        (folder / "page.html").write_text(self.html, encoding="utf-8")
        for name, attr in _SCREENSHOTS:
            image = getattr(self, attr)
            if image is not None:
                (folder / f"{name}.{image_extension(image)}").write_bytes(image)
        for number, state in enumerate(self.states, start=1):
            if state.page.screenshot is not None:
                image = state.page.screenshot
                (folder / f"state-{number}.{image_extension(image)}").write_bytes(image)
        return folder

    @classmethod
    def load(cls, folder: str | Path) -> PageSnapshot:
        folder = Path(folder)
        data = json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
        html_file = folder / "page.html"
        html = html_file.read_text(encoding="utf-8") if html_file.is_file() else ""
        snapshot = cls.from_dict(data, html=html)
        for name, attr in _SCREENSHOTS:
            image = _image(folder, name)
            if image is not None:
                setattr(snapshot, attr, image)
        for number, state in enumerate(snapshot.states, start=1):
            state.page.screenshot = _image(folder, f"state-{number}")
        return snapshot

    def folder_name(self) -> str:
        """A file-system friendly name for this page and viewport."""
        slug = re.sub(r"^https?://", "", self.url)
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", slug).strip("_")[:80] or "page"
        return f"{slug}@{self.viewport}"


def _image(folder: Path, stem: str) -> bytes | None:
    for extension in ("jpg", "png"):
        path = folder / f"{stem}.{extension}"
        if path.is_file():
            return path.read_bytes()
    return None
