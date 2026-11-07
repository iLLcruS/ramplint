"""Rules that compare the pages of a crawl (browser mode): RL901-RL904.

A crawl sees many pages at once, so it can check what no single page can:
whether the pages agree with each other. Results never depend on the order the
pages were crawled in: pages are sorted by URL and ties are broken by URL.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ramplint.browser.urls import normalize_url, url_pattern
from ramplint.rules.base import SiteFinding, site_rule

if TYPE_CHECKING:
    from ramplint.browser.snapshot import PageSnapshot
    from ramplint.dom import Node

_SPACE_RE = re.compile(r"\s+")
_LANDMARKS = {tag: tag for tag in ("nav", "header", "footer", "aside", "main")}
_LANDMARK_ROLES = {
    "navigation": "nav", "banner": "header", "contentinfo": "footer",
    "complementary": "aside", "main": "main",
}  # fmt: skip
#: Links before the main content that make a block worth skipping.
BYPASS_MIN_LINKS = 3


def _pages(snapshots: Sequence[PageSnapshot]) -> list[PageSnapshot]:
    """One snapshot per page (the first viewport), sorted by URL.

    A URL that redirected to another path (``/profile/`` to the login page)
    showed that other page, not a page of its own, so it is left out.
    """
    by_url: dict[str, PageSnapshot] = {}
    for snapshot in snapshots:
        if not snapshot.is_html or not snapshot.html or (snapshot.status or 200) >= 400:
            continue
        final = urlsplit(snapshot.final_url or snapshot.url).path.rstrip("/")
        if final != urlsplit(snapshot.url).path.rstrip("/"):
            continue
        by_url.setdefault(snapshot.url, snapshot)
    return [by_url[url] for url in sorted(by_url)]


def _clean(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def _node_id(node: Node | None) -> str | None:
    return node.get("data-rl-node") if node is not None else None


def _quote_pages(urls: Sequence[str], limit: int = 3) -> str:
    shown = ", ".join(urls[:limit])
    return shown + (f" and {len(urls) - limit} more" if len(urls) > limit else "")


# -- RL901 page-title-unique ---------------------------------------------------------


@site_rule(
    "RL901",
    "page-title-unique",
    "Different pages must have different titles.",
    "2.4.2 Page Titled (A)",
)
def page_title_unique(snapshots: Sequence[PageSnapshot]) -> Iterator[SiteFinding]:
    groups: dict[str, list[PageSnapshot]] = defaultdict(list)
    for page in _pages(snapshots):
        title = _clean(page.title).lower()
        if title:
            groups[title].append(page)
    for pages in groups.values():
        patterns = {url_pattern(page.url) for page in pages}
        if len(patterns) < 2:
            continue  # the same kind of page (e.g. ?page=2) may share a title
        first = pages[0]
        title_node = next(first.tree.root.iter("title"), None)
        urls = [page.url for page in pages]
        yield SiteFinding(
            first,
            _node_id(title_node),
            f'{len(pages)} different pages are all titled "{_clean(first.title)}" '
            f"({_quote_pages(urls)}); give each page a title that says what it is",
            tuple(urls),
        )


# -- RL902 consistent-navigation ----------------------------------------------------


def _label(page: PageSnapshot, node: Node) -> str:
    label = node.get("aria-label")
    if label:
        return _clean(label).lower()
    labelledby = node.get("aria-labelledby")
    if labelledby:
        for target in page.tree.root.iter():
            if target.get("id") in labelledby.split():
                return _clean(target.text()).lower()
    return ""


def _navigations(page: PageSnapshot) -> dict[str, list[str]]:
    """Each ``<nav>`` (by label, else by position) and its link targets in order."""
    navs: dict[str, list[str]] = {}
    position = 0
    for node in page.tree.root.iter():
        if node.tag != "nav" and node.get("role") != "navigation":
            continue
        position += 1
        key = _label(page, node) or f"#{position}"
        links = []
        for link in node.iter("a"):
            href = link.get("href")
            url = normalize_url(href, page.final_url or page.url) if href else None
            if url and url not in links:
                links.append(url)
        navs.setdefault(key, links)
    return navs


def _relative_order(links: list[str], common: set[str]) -> tuple[str, ...]:
    return tuple(link for link in links if link in common)


@site_rule(
    "RL902",
    "consistent-navigation",
    "Navigation repeated on several pages must keep its links in the same order.",
    "3.2.3 Consistent Navigation (AA)",
)
def consistent_navigation(snapshots: Sequence[PageSnapshot]) -> Iterator[SiteFinding]:
    pages = _pages(snapshots)
    by_nav: dict[str, list[tuple[PageSnapshot, list[str]]]] = defaultdict(list)
    for page in pages:
        for key, links in _navigations(page).items():
            if len(links) >= 2:
                by_nav[key].append((page, links))
    for key, entries in sorted(by_nav.items()):
        if len(entries) < 2:
            continue
        common = set(entries[0][1]).intersection(*(set(links) for _, links in entries[1:]))
        if len(common) < 2:
            continue
        orders = Counter(_relative_order(links, common) for _, links in entries)
        reference = max(orders, key=lambda order: (orders[order], order))
        differing = [page for page, links in entries if _relative_order(links, common) != reference]
        if not differing:
            continue
        name = f'"{key}"' if not key.startswith("#") else f"number {key[1:]}"
        nav_node = _nav_node(differing[0], key)
        yield SiteFinding(
            differing[0],
            _node_id(nav_node),
            f"Navigation {name} lists the same links in a different order on "
            f"{_quote_pages([p.url for p in differing])} than on the other pages; "
            "keep repeated navigation in the same order",
            tuple(sorted(page.url for page, _ in entries)),
        )


def _nav_node(page: PageSnapshot, key: str) -> Node | None:
    position = 0
    for node in page.tree.root.iter():
        if node.tag == "nav" or node.get("role") == "navigation":
            position += 1
            if (_label(page, node) or f"#{position}") == key:
                return node
    return None


# -- RL903 consistent-identification --------------------------------------------------


def _region(node: Node) -> str:
    """The landmark a control sits in (``nav main``, ``footer``...)."""
    for ancestor in node.ancestors():
        region = _LANDMARKS.get(ancestor.tag) or _LANDMARK_ROLES.get(ancestor.get("role") or "")
        if region:
            label = ancestor.get("aria-label") or ""
            return f"{region} {_clean(label).lower()}".strip()
    return "page"


def _name(page: PageSnapshot, node: Node) -> str:
    element = page.element(_node_id(node))
    if element is not None and element.name is not None:
        return _clean(element.name)
    return _clean(node.get("aria-label") or node.text())


def _icon(node: Node) -> str | None:
    for child in node.iter("img", "use"):
        source = child.get("src") or child.get("href") or child.get("xlink:href")
        if source:
            return source
    return None


@site_rule(
    "RL903",
    "consistent-identification",
    "Controls that do the same thing on different pages must have the same name.",
    "3.2.4 Consistent Identification (AA)",
)
def consistent_identification(snapshots: Sequence[PageSnapshot]) -> Iterator[SiteFinding]:
    # (what it is, where it is) -> name -> pages, and the first element per page.
    names: dict[tuple[str, str], dict[str, list[PageSnapshot]]] = defaultdict(
        lambda: defaultdict(list)
    )
    nodes: dict[tuple[str, str, str], Node] = {}
    for page in _pages(snapshots):
        seen: set[tuple[str, str]] = set()
        for node in page.tree.root.iter("a", "button"):
            if node.tag == "a":
                href = (node.get("href") or "").strip()
                in_page = not href or href.startswith("#")  # skip links, tabs
                target = None if in_page else normalize_url(href, page.final_url or page.url)
                identity = f"link to {target}" if target else None
            else:
                icon = _icon(node)
                identity = f"button with icon {icon}" if icon else None
            name = _name(page, node)
            if identity is None or not name:
                continue
            key = (identity, _region(node))
            if key in seen:
                continue  # the first one on a page stands for it
            seen.add(key)
            names[key][name.lower()].append(page)
            nodes.setdefault((*key, page.url), node)
    for (identity, region), by_name in sorted(names.items()):
        if len(by_name) < 2:
            continue
        variants = sorted(by_name.items(), key=lambda item: (-len(item[1]), item[0]))
        odd_page = variants[-1][1][0]
        node = nodes[(identity, region, odd_page.url)]
        described = ", ".join(
            f'"{_name(pages[0], nodes[(identity, region, pages[0].url)])}" '
            f"({len(pages)} page{'s' if len(pages) != 1 else ''})"
            for _, pages in variants
        )
        where = f" in the {region}" if region != "page" else ""
        yield SiteFinding(
            odd_page,
            _node_id(node),
            f"The {identity}{where} is named differently on different pages: {described}; "
            "use the same name everywhere",
            tuple(sorted({page.url for _, pages in variants for page in pages})),
        )


# -- RL904 bypass-blocks -------------------------------------------------------------


def _main(page: PageSnapshot) -> Node | None:
    for node in page.tree.root.iter():
        if node.tag == "main" or node.get("role") == "main":
            return node
    return None


def _links_before_main(page: PageSnapshot) -> list[tuple[Node, str]]:
    """Links in document order until the main content (or the first heading)."""
    links = []
    for node in page.tree.root.iter():
        if node.tag == "main" or node.get("role") == "main" or node.tag == "h1":
            break
        if node.tag == "a" and node.get("href"):
            links.append((node, node.attrs["href"]))
    return links


def _has_skip_link(page: PageSnapshot, links: list[tuple[Node, str]]) -> bool:
    ids = {node.get("id") for node in page.tree.root.iter() if node.get("id")}
    return any(href.startswith("#") and href[1:] in ids for _, href in links[:3])


@site_rule(
    "RL904",
    "bypass-blocks",
    "Pages with repeated navigation must offer a way to skip it.",
    "2.4.1 Bypass Blocks (A)",
)
def bypass_blocks(snapshots: Sequence[PageSnapshot]) -> Iterator[SiteFinding]:
    pages = _pages(snapshots)
    blocks: dict[tuple[str, ...], list[PageSnapshot]] = defaultdict(list)
    first_link: dict[str, Node] = {}
    for page in pages:
        links = _links_before_main(page)
        if len(links) < BYPASS_MIN_LINKS or _main(page) is not None:
            continue
        if _has_skip_link(page, links):
            continue
        base = page.final_url or page.url
        block = tuple(normalize_url(href, base) or href for _, href in links)
        blocks[block].append(page)
        first_link[page.url] = links[0][0]
    for block, failing in sorted(blocks.items()):
        if len(failing) < 2:
            continue  # navigation seen on one page only is not "repeated"
        first = failing[0]
        yield SiteFinding(
            first,
            _node_id(first_link[first.url]),
            f"{len(block)} links come before the content on {len(failing)} pages "
            f"({_quote_pages([p.url for p in failing])}) with no skip link and no <main>; "
            'add <a href="#content">Skip to content</a> or wrap the content in <main>',
            tuple(page.url for page in failing),
        )
