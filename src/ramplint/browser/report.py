"""The browser report folder (``ramplint URL --format html -o a11y/``).

::

    a11y/
      index.html       every problem (the usual HTML report), by template or URL pattern
      pages/*.html     one page per URL and viewport: screenshot with numbered markers,
                       the problems in order with a picture of each element
      site-map.html    URL patterns and what the crawl did with each
      api.html         XHR / fetch endpoints the pages called
      screenshots/     the images
      scan.json        all of it for tools and --baseline

Every page works offline, needs no JavaScript (only the filters use it) and
passes ramplint. Screenshots are written while the browser is still open
(:class:`ScreenshotStore`); the pages are written after the crawl.
"""

from __future__ import annotations

import base64
import json
import re
import threading
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from html import escape
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ramplint import __version__
from ramplint.browser.snapshot import Box, PageSnapshot, image_extension
from ramplint.html_report import _CSS, _rule_link, folder_nav, report_html
from ramplint.linter import Violation
from ramplint.reporters import browser_report

if TYPE_CHECKING:
    from ramplint.browser.scan import ScanResult
    from ramplint.browser.session import BrowserSession

SCAN_SCHEMA = 1
#: Above this, ``--embed-screenshots`` warns that the file is large.
EMBED_WARNING_BYTES = 20 * 1024 * 1024
NAV = (
    ("Problems", "index.html"),
    ("Site map", "site-map.html"),
    ("API calls", "api.html"),
)


def slug(url: str, viewport: str) -> str:
    """File name of a page report: ``localhost_8000_products_1@desktop``."""
    text = re.sub(r"^https?://", "", url)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")[:90] or "page"
    return f"{text}@{viewport}"


@dataclass
class PageShot:
    url: str
    viewport: str
    title: str
    status: int | None
    page_size: tuple[int, int]
    #: Relative to the report folder, ``None`` without a screenshot.
    image: str | None
    #: The page's own problems (before merging across pages) and their pictures.
    problems: list[tuple[Violation, str | None]] = field(default_factory=list)


class ScreenshotStore:
    """Saves screenshots and element pictures during a crawl (``Crawler.on_page``)."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.images = folder / "screenshots"
        self.pages: dict[tuple[str, str], PageShot] = {}
        self._crops: dict[tuple[object, ...], str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(v: Violation) -> tuple[object, ...]:
        return (v.path, v.code, v.selector, v.message, v.state)

    def _write(self, name: str, data: bytes) -> str:
        self.images.mkdir(parents=True, exist_ok=True)
        path = self.images / f"{name}.{image_extension(data)}"
        path.write_bytes(data)
        return path.relative_to(self.folder).as_posix()

    def on_page(
        self, session: BrowserSession, snapshot: PageSnapshot, violations: list[Violation]
    ) -> None:
        if not snapshot.is_html:
            return
        name = slug(snapshot.url, snapshot.viewport)
        image = self._write(name, snapshot.full_screenshot) if snapshot.full_screenshot else None
        crops = self._crops_for(session, snapshot, violations)
        shot = PageShot(
            url=snapshot.url,
            viewport=snapshot.viewport,
            title=snapshot.title,
            status=snapshot.status,
            page_size=snapshot.page_size,
            image=image,
        )
        for number, (violation, crop) in enumerate(zip(violations, crops, strict=True), 1):
            path = self._write(f"{name}-{number}", crop) if crop else None
            shot.problems.append((violation, path))
            if path:
                with self._lock:
                    self._crops.setdefault(self._key(violation), path)
        with self._lock:
            self.pages[(snapshot.url, snapshot.viewport)] = shot

    @staticmethod
    def _crops_for(
        session: BrowserSession, snapshot: PageSnapshot, violations: list[Violation]
    ) -> list[bytes | None]:
        """A picture per problem: from the page, or from the state it was found in."""
        result: list[bytes | None] = [None] * len(violations)
        sources: dict[str | None, PageSnapshot] = {None: snapshot}
        for state in snapshot.states:
            # States have a viewport screenshot; crops come from it.
            sources[state.description] = replace(state.page, full_screenshot=state.page.screenshot)
        groups: dict[str | None, list[int]] = defaultdict(list)
        for index, v in enumerate(violations):
            if v.bbox is not None and v.state in sources:
                groups[v.state].append(index)
        for state, indexes in groups.items():
            boxes: list[Box] = [violations[i].bbox for i in indexes]  # type: ignore[misc]
            for index, crop in zip(indexes, session.crops(sources[state], boxes), strict=True):
                result[index] = crop
        return result

    def with_pictures(self, violations: Sequence[Violation]) -> list[Violation]:
        """``violations`` with ``screenshot`` set to a picture of the (first) element."""
        return [replace(v, screenshot=self._crops.get(self._key(v))) for v in violations]


# -- pages ---------------------------------------------------------------------------


def _shell(title: str, current: str, depth: int, body: str, heading: str, meta: str) -> str:
    prefix = "../" * depth
    nav = folder_nav([(label, prefix + href) for label, href in NAV], current)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="generator" content="ramplint">\n'
        f"<title>{escape(title)} - ramplint report</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n<body>\n"
        f'<header class="sign"><div class="wrap">{nav}'
        f"<h1>{escape(heading)}</h1>"
        f'<p class="meta">{meta}</p>'
        "</div></header>\n"
        f'<main class="wrap">{body}</main>\n'
        '<footer class="wrap">Generated by '
        f'<a href="https://github.com/iLLcruS/ramplint">ramplint</a> {escape(__version__)}.'
        "</footer>\n</body>\n</html>\n"
    )


def _has_marker(v: Violation, shot: PageShot) -> bool:
    """Only elements with an area on the page screenshot get a marker."""
    return bool(shot.image and v.bbox and not v.state and v.bbox[2] > 0 and v.bbox[3] > 0)


def _markers(shot: PageShot) -> str:
    width, height = shot.page_size
    if not shot.image or width <= 0 or height <= 0:
        return ""
    marks = []
    for number, (v, _) in enumerate(shot.problems, 1):
        if not _has_marker(v, shot):
            continue
        x, y, w, h = v.bbox
        style = (
            f"left:{100 * x / width:.3f}%;top:{100 * y / height:.3f}%;"
            f"width:{100 * w / width:.3f}%;height:{100 * h / height:.3f}%"
        )
        marks.append(
            f'<span class="marker" id="marker-{number}" style="{style}"><b>{number}</b></span>'
        )
    return (
        '<figure class="shot">'
        f'<img src="../{escape(shot.image)}" alt="Screenshot of the page">'
        f'<div aria-hidden="true">{"".join(marks)}</div>'
        "</figure>"
    )


def page_report(shot: PageShot) -> str:
    items = []
    for number, (v, crop) in enumerate(shot.problems, 1):
        where = [f'<code class="selector">{escape(v.selector)}</code>'] if v.selector else []
        if v.template:
            where.append(f'<p class="pages">{escape(v.template)}</p>')
        if v.state:
            where.append(f'<p class="pages">{escape(v.state)}</p>')
        picture = f'<img class="crop" src="../{escape(crop)}" alt="">' if crop else ""
        marker = f' <a href="#marker-{number}">Marker {number}</a>' if _has_marker(v, shot) else ""
        items.append(
            f'<li id="problem-{number}"><span class="code">{escape(v.code)}</span> '
            f"{escape(v.message)}{marker}{_rule_link(v.code, v.name)}{''.join(where)}{picture}"
            "</li>"
        )
    problems = (
        f'<ol class="page-problems">{"".join(items)}</ol>'
        if items
        else '<p class="clean">No problems on this page.</p>'
    )
    count = len(shot.problems)
    body = (
        '<section class="box" aria-labelledby="problems-title">'
        f'<h2 id="problems-title">{count} problem{"s" if count != 1 else ""}</h2>'
        f"{problems}</section>"
        '<section aria-labelledby="shot-title">'
        f'<h2 id="shot-title">Screenshot ({escape(shot.viewport)})</h2>'
        f"{_markers(shot) or '<p>No screenshot.</p>'}</section>"
    )
    meta = f'<a href="{escape(shot.url)}">{escape(shot.url)}</a> at {escape(shot.viewport)}'
    return _shell(shot.title or shot.url, "", 1, body, shot.title or shot.url, meta)


def _status_class(status: str) -> str:
    return "status status-" + status.replace(" ", "-")


def site_map(result: ScanResult, page_links: dict[str, str]) -> str:
    tree: dict[str, list] = defaultdict(list)
    for coverage in result.coverage:
        segments = [s for s in coverage.route.split("/") if s]
        tree[segments[0] if segments else "/"].append(coverage)
    groups = []
    for top in sorted(tree):
        rows = []
        for coverage in tree[top]:
            details = []
            if coverage.name:
                details.append(f"<code>{escape(coverage.name)}</code>")
            if coverage.source:
                details.append(escape(coverage.source))
            for url in coverage.scanned[:5]:
                href = page_links.get(url, url)
                details.append(f'<a href="{escape(href)}">{escape(urlsplit(url).path or "/")}</a>')
            for url, status in sorted(coverage.results.items()):
                details.append(f"{escape(urlsplit(url).path)}: {escape(status)}")
            for url, target in sorted(coverage.redirects.items()):
                details.append(f"{escape(urlsplit(url).path)} → {escape(target)}")
            rows.append(
                f"<li><code>{escape(coverage.route)}</code> "
                f'<span class="{_status_class(coverage.status)}">{escape(coverage.summary)}</span>'
                f"{' · ' + ' · '.join(details) if details else ''}</li>"
            )
        label = "/" if top == "/" else f"/{top}/"
        groups.append(f"<li><code>{escape(label)}</code><ul>{''.join(rows)}</ul></li>")
    counts: dict[str, int] = defaultdict(int)
    for coverage in result.coverage:
        counts[coverage.status] += 1
    summary = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
    body = (
        '<section class="box" aria-labelledby="map-title">'
        f'<h2 id="map-title">URL patterns</h2><p>{escape(summary)}</p>'
        f'<ul class="tree">{"".join(groups)}</ul></section>'
    )
    return _shell(
        "Site map", "Site map", 0, body, "Site map", f"{len(result.coverage)} URL patterns"
    )


def api_inventory(result: ScanResult) -> str:
    if result.endpoints:
        rows = "".join(
            "<tr>"
            f"<td><code>{escape(e.method)}</code></td>"
            f'<th scope="row"><code>{escape(e.pattern)}</code></th>'
            f"<td>{escape(', '.join(map(str, sorted(e.statuses))) or 'failed')}</td>"
            f"<td>{escape(', '.join(sorted(e.content_types)))}</td>"
            f"<td>{len(e.pages)}</td>"
            "</tr>"
            for e in result.endpoints
        )
        table = (
            "<table><caption>XHR and fetch requests made while the pages loaded</caption>"
            '<thead><tr><th scope="col">Method</th><th scope="col">URL pattern</th>'
            '<th scope="col">Status</th><th scope="col">Content type</th>'
            '<th scope="col" class="num">Pages</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        table = "<p>The pages made no XHR or fetch requests.</p>"
    actions = ""
    if result.actions:
        listed = "".join(
            f"<li><code>{escape(a.method)} {escape(a.url)}</code></li>" for a in result.actions
        )
        actions = (
            '<section class="box" aria-labelledby="actions-title">'
            '<h2 id="actions-title">Requests controls would send (never sent)</h2>'
            f"<ul>{listed}</ul></section>"
        )
    body = (
        f'<section class="box" aria-labelledby="api-title"><h2 id="api-title">Endpoints</h2>'
        f"{table}</section>{actions}"
    )
    return _shell(
        "API calls", "API calls", 0, body, "API calls", f"{len(result.endpoints)} endpoints"
    )


# -- scan.json -----------------------------------------------------------------------


def scan_data(
    result: ScanResult,
    violations: Sequence[Violation],
    start_urls: Sequence[str],
    viewports: Sequence[str],
) -> dict[str, object]:
    """Everything the report shows, for tools and ``--baseline``."""
    from ramplint.browser.baseline import fingerprint

    return {
        "schema": SCAN_SCHEMA,
        "tool": {"name": "ramplint", "version": __version__},
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start_urls": list(start_urls),
        "viewports": list(viewports),
        "pages": [
            {
                "url": s.url,
                "viewport": s.viewport,
                "final_url": s.final_url,
                "status": s.status,
                "title": s.title,
                "error": s.error or None,
                "redirects": s.redirects,
                "states": [state.description for state in s.states],
            }
            for s in result.snapshots
        ],
        "violations": [{**v.to_dict(), "fingerprint": fingerprint(v)} for v in violations],
        "coverage": [c.to_dict() for c in result.coverage],
        "endpoints": [e.to_dict() for e in result.endpoints],
        "actions": [{"method": a.method, "url": a.url} for a in result.actions],
        "fragments": result.fragments,
        "manual_checks": [
            {"url": m.url, "selector": m.selector, "code": m.code, "message": m.message}
            for m in result.manual
        ],
    }


def write_scan_json(path: Path, data: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


# -- the folder ----------------------------------------------------------------------


def write_folder(
    folder: Path,
    result: ScanResult,
    violations: Sequence[Violation],
    store: ScreenshotStore,
    start_urls: Sequence[str],
    viewports: Sequence[str],
    fixed: Sequence[dict[str, object]] = (),
) -> Path:
    """Write the report folder; returns the path of ``index.html``."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pages").mkdir(exist_ok=True)
    shots = sorted(store.pages.values(), key=lambda s: (s.url, viewports.index(s.viewport)))
    page_links: dict[str, str] = {}
    for shot in shots:
        href = f"pages/{slug(shot.url, shot.viewport)}.html"
        page_links.setdefault(shot.url, href)
        (folder / href).write_text(page_report(shot), encoding="utf-8")
    pictured = store.with_pictures(violations)
    out = StringIO()
    with browser_report(viewports, page_links, NAV, fixed):
        report_html(pictured, result.pages_checked, out)
    index = folder / "index.html"
    index.write_text(out.getvalue(), encoding="utf-8")
    (folder / "site-map.html").write_text(site_map(result, page_links), encoding="utf-8")
    (folder / "api.html").write_text(api_inventory(result), encoding="utf-8")
    write_scan_json(folder / "scan.json", scan_data(result, pictured, start_urls, viewports))
    return index


def write_single(
    target: Path,
    result: ScanResult,
    violations: Sequence[Violation],
    store: ScreenshotStore,
    viewports: Sequence[str],
    fixed: Sequence[dict[str, object]] = (),
) -> int:
    """``--embed-screenshots``: one HTML file with the pictures inlined; returns its size."""

    def data_uri(relative: str | None) -> str | None:
        if relative is None:
            return None
        image = store.folder / relative
        mime = "image/png" if image.suffix == ".png" else "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(image.read_bytes()).decode('ascii')}"

    pictured = [
        replace(v, screenshot=data_uri(v.screenshot)) for v in store.with_pictures(violations)
    ]
    out = StringIO()
    with browser_report(viewports, fixed=fixed):
        report_html(pictured, result.pages_checked, out)
    html = out.getvalue()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return len(html.encode("utf-8"))
