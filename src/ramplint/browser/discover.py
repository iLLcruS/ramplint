"""Find more pages: links in rendered pages, ``robots.txt`` and sitemaps.

Everything here works on text that was already fetched, so it is tested
without a browser. Links are read from the rendered HTML (with what JavaScript
added) and resolved against the page's final URL and ``<base href>``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterator
from dataclasses import dataclass

from ramplint import dom
from ramplint.browser.urls import normalize_url

#: HTMX attributes that send a request when the user acts; never called.
_HX_ACTIONS = ("hx-post", "hx-put", "hx-patch", "hx-delete")
_REFRESH_RE = re.compile(r"^\s*\d*(?:\.\d+)?\s*[;,]\s*url\s*=\s*['\"]?([^'\"]+)", re.I)
_SITEMAP_LINE_RE = re.compile(r"^\s*sitemap\s*:\s*(\S+)", re.I | re.M)
#: A sitemap must not make ramplint expand entities or fetch DTDs.
_UNSAFE_XML_RE = re.compile(r"<!(?:DOCTYPE|ENTITY)", re.I)


@dataclass(frozen=True)
class Link:
    """A URL found in a page and how: ``a``, ``area``, ``link``, ``iframe``,
    ``form``, ``refresh`` or ``hx-get`` (an HTML fragment)."""

    url: str
    kind: str

    @property
    def fragment(self) -> bool:
        """HTMX loads the response into a page: it is a partial, not a page."""
        return self.kind == "hx-get"


@dataclass(frozen=True)
class Action:
    """A request a control would send (``hx-post`` and friends); listed, never sent."""

    method: str
    url: str


@dataclass
class PageLinks:
    links: list[Link]
    actions: list[Action]


def _base_url(root: dom.Node, page_url: str) -> str:
    base = next(root.iter("base"), None)
    href = base.get("href") if base is not None else None
    return normalize_url(href, page_url) or page_url if href else page_url


def _attribute(node: dom.Node, name: str) -> str | None:
    """``hx-get`` or ``data-hx-get``."""
    return node.get(name) or node.get(f"data-{name}")


def _candidates(root: dom.Node) -> Iterator[tuple[str, str]]:
    """``(raw URL, kind)`` for every element that leads somewhere with GET."""
    for node in root.iter():
        tag = node.tag
        if tag in ("a", "area") and node.has_value("href") and "download" not in node.attrs:
            yield node.attrs["href"], tag
        elif tag == "link" and node.has_value("href"):
            rel = (node.get("rel") or "").lower().split()
            if "next" in rel or "prev" in rel:
                yield node.attrs["href"], "link"
        elif tag == "iframe" and node.has_value("src"):
            yield node.attrs["src"], "iframe"
        elif tag == "form" and (node.get("method") or "get").strip().lower() == "get":
            # Submitted without values: the page the form leads to.
            if node.has_value("action"):
                yield node.attrs["action"], "form"
        elif tag == "meta" and (node.get("http-equiv") or "").lower() == "refresh":
            match = _REFRESH_RE.match(node.get("content") or "")
            if match:
                yield match.group(1), "refresh"
        hx_get = _attribute(node, "hx-get")
        if hx_get:
            yield hx_get, "hx-get"


def page_links(html: str, page_url: str) -> PageLinks:
    """Links and HTMX actions of a rendered page, normalized and without duplicates."""
    root = dom.parse(html)
    base = _base_url(root, page_url)
    links: dict[tuple[str, str], Link] = {}
    for raw, kind in _candidates(root):
        url = normalize_url(raw, base)
        if url is not None and url != normalize_url(page_url):
            links.setdefault((url, kind), Link(url, kind))
    actions: dict[tuple[str, str], Action] = {}
    for node in root.iter():
        for attribute in _HX_ACTIONS:
            raw = _attribute(node, attribute)
            url = normalize_url(raw, base) if raw else None
            if url is not None:
                method = attribute.removeprefix("hx-").upper()
                actions.setdefault((method, url), Action(method, url))
    return PageLinks(list(links.values()), list(actions.values()))


# -- robots.txt and sitemaps ----------------------------------------------------


def robots_sitemaps(text: str, base: str) -> list[str]:
    """The ``Sitemap:`` URLs of a ``robots.txt``."""
    found = (normalize_url(m.group(1), base) for m in _SITEMAP_LINE_RE.finditer(text))
    return list(dict.fromkeys(url for url in found if url))


@dataclass
class Sitemap:
    #: Page URLs (``<urlset>``).
    pages: list[str]
    #: Child sitemaps (``<sitemapindex>``).
    sitemaps: list[str]


def parse_sitemap(text: str, base: str) -> Sitemap:
    """Pages and child sitemaps of a sitemap; empty for anything that is not one."""
    if _UNSAFE_XML_RE.search(text):
        return Sitemap([], [])
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return Sitemap([], [])
    locations = [
        normalize_url(element.text, base)
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "loc" and element.text
    ]
    urls = list(dict.fromkeys(url for url in locations if url))
    if root.tag.rsplit("}", 1)[-1] == "sitemapindex":
        return Sitemap([], urls)
    return Sitemap(urls, [])
