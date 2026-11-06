"""What ramplint knows about one rendered page in one viewport.

A :class:`PageSnapshot` is captured once by :mod:`ramplint.browser.session`;
checks and reports only read it. ``save()`` / ``load()`` keep it on disk, which
is how the tests check rules without starting a browser.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SNAPSHOT_SCHEMA = 1

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

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("screenshot")
        data.pop("full_screenshot")
        data.pop("html")
        data["elements"] = [asdict(e) for e in self.elements.values()]
        return {"schema": SNAPSHOT_SCHEMA, **data}

    @classmethod
    def from_dict(cls, data: dict[str, Any], html: str = "") -> PageSnapshot:
        data = dict(data)
        if data.pop("schema", SNAPSHOT_SCHEMA) != SNAPSHOT_SCHEMA:
            raise ValueError("unsupported snapshot schema")
        elements = {}
        for raw in data.pop("elements", []):
            raw["box"] = tuple(raw["box"])
            elements[raw["id"]] = ElementInfo(**raw)
        data["page_size"] = tuple(data.get("page_size", (0, 0)))
        return cls(**data, elements=elements, html=html)

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
        return folder

    @classmethod
    def load(cls, folder: str | Path) -> PageSnapshot:
        folder = Path(folder)
        data = json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
        html_file = folder / "page.html"
        html = html_file.read_text(encoding="utf-8") if html_file.is_file() else ""
        snapshot = cls.from_dict(data, html=html)
        for name, attr in _SCREENSHOTS:
            for extension in ("jpg", "png"):
                image = folder / f"{name}.{extension}"
                if image.is_file():
                    setattr(snapshot, attr, image.read_bytes())
                    break
        return snapshot

    def folder_name(self) -> str:
        """A file-system friendly name for this page and viewport."""
        slug = re.sub(r"^https?://", "", self.url)
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", slug).strip("_")[:80] or "page"
        return f"{slug}@{self.viewport}"
