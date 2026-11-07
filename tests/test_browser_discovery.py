"""Finding pages: links, sitemaps, URL normalization - no browser needed."""

from __future__ import annotations

import pytest

from ramplint.browser.discover import Action, Link, page_links, parse_sitemap, robots_sitemaps
from ramplint.browser.urls import normalize_url, origin, same_origin, url_key

PAGE = "http://shop.test/catalog/"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("/a/b/../c/", "http://shop.test/a/c/"),
        ("../x", "http://shop.test/x"),
        ("?b=2&a=1#top", "http://shop.test/catalog/?a=1&b=2"),
        ("/p/?utm_source=x&id=3&fbclid=y&gclid=z", "http://shop.test/p/?id=3"),
        ("HTTP://Shop.Test:80/Case/", "http://shop.test/Case/"),
        ("https://shop.test:443/", "https://shop.test/"),
        ("http://shop.test:8000", "http://shop.test:8000/"),
        ("//cdn.test/lib.js", "http://cdn.test/lib.js"),
        ("mailto:a@b.c", None),
        ("javascript:void(0)", None),
        ("tel:+40", None),
        ("/a//b/", "http://shop.test/a/b/"),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw, PAGE) == expected


def test_urls_without_host():
    assert normalize_url("http:///nohost") is None
    assert normalize_url("relative/only") is None


def test_origins_and_keys():
    assert origin("https://A.test:443/x") == "https://a.test"
    assert origin("http://a.test:8000/") == "http://a.test:8000"
    assert same_origin("http://a.test/x", "http://a.test:80/y")
    assert not same_origin("http://a.test/", "https://a.test/")
    assert url_key("http://a.test/x/") == url_key("http://a.test/x")
    assert url_key("http://a.test/") == "http://a.test/"


HTML = """<!DOCTYPE html><html><head>
<link rel="next" href="?page=2"><link rel="stylesheet" href="/s.css">
<meta http-equiv="refresh" content="5; url=/moved/">
</head><body>
<a href="/products/1/">One</a>
<a href="/products/1/#reviews">Same page, other anchor</a>
<a href="mailto:shop@shop.test">Mail</a>
<a href="/files/menu.pdf" download>Download</a>
<a href="#top">Top</a>
<map><area href="/map/" alt="Map"></map>
<iframe src="/embed/" title="Embed"></iframe>
<form action="/search/"><input name="q"></form>
<form method="post" action="/cart/add/"><button>Add</button></form>
<form method="GET"><input name="nothing"></form>
<div hx-get="/fragments/cart/" hx-trigger="load"></div>
<button data-hx-delete="/cart/1/">Remove</button>
<button hx-post="/cart/clear/">Clear</button>
</body></html>"""


def test_page_links():
    found = page_links(HTML, PAGE)
    assert found.links == [
        Link("http://shop.test/catalog/?page=2", "link"),
        Link("http://shop.test/moved/", "refresh"),
        Link("http://shop.test/products/1/", "a"),
        Link("http://shop.test/map/", "area"),
        Link("http://shop.test/embed/", "iframe"),
        Link("http://shop.test/search/", "form"),
        Link("http://shop.test/fragments/cart/", "hx-get"),
    ]
    assert [link.url for link in found.links if link.fragment] == [
        "http://shop.test/fragments/cart/"
    ]
    assert found.actions == [
        Action("DELETE", "http://shop.test/cart/1/"),
        Action("POST", "http://shop.test/cart/clear/"),
    ]


def test_base_href():
    found = page_links('<base href="/v2/"><a href="items/">x</a>', "http://a.test/old/page/")
    assert found.links == [Link("http://a.test/v2/items/", "a")]


def test_robots_sitemaps():
    text = "User-agent: *\nDisallow: /admin/\nSitemap: /sitemap-index.xml\nsitemap: https://a.test/s2.xml\n"
    assert robots_sitemaps(text, "https://a.test") == [
        "https://a.test/sitemap-index.xml",
        "https://a.test/s2.xml",
    ]


def test_sitemaps():
    urlset = (
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://a.test/a/</loc></url><url><loc> /b/ </loc></url>"
        "<url><loc>https://a.test/a/</loc></url></urlset>"
    )
    assert parse_sitemap(urlset, "https://a.test/sitemap.xml").pages == [
        "https://a.test/a/",
        "https://a.test/b/",
    ]
    index = (
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<sitemap><loc>https://a.test/s1.xml</loc></sitemap></sitemapindex>"
    )
    parsed = parse_sitemap(index, "https://a.test/")
    assert parsed.sitemaps == ["https://a.test/s1.xml"] and parsed.pages == []


@pytest.mark.parametrize(
    "text",
    [
        "not xml at all",
        '<!DOCTYPE x [<!ENTITY a "aaaa">]><urlset><url><loc>&a;</loc></url></urlset>',
    ],
)
def test_bad_or_unsafe_sitemaps_are_empty(text):
    parsed = parse_sitemap(text, "https://a.test/")
    assert parsed.pages == [] and parsed.sitemaps == []
