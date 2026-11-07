"""The crawl frontier and the crawler, against a fake site (no browser)."""

from __future__ import annotations

import pytest
from fakes import FakeBrowser, FakePage, links_page

from ramplint.browser.frontier import Frontier, PatternInference, Source, Status, start_urls
from ramplint.browser.options import BrowserOptions
from ramplint.browser.scan import Crawler
from ramplint.browser.session import Fetched
from ramplint.browser.snapshot import NetworkRecord, PageSnapshot
from ramplint.project.urls import RoutePart, UrlConf, UrlPattern
from ramplint.rules import select_rules

SITE = "http://shop.test"


def crawl(site, *, start=f"{SITE}/", files=None, extra=(), urlconf=None, login=None, **options):
    browser = FakeBrowser(site, files)
    defaults = {"timeout": 5.0}
    crawler = Crawler(
        select_rules(),
        BrowserOptions(**{**defaults, **options}),
        urlconf=urlconf,
        login_path=login,
        session_factory=browser.factory,
    )
    return crawler.run([start], list(extra)), browser


def product_site(count: int = 500) -> dict:
    products = [f"/products/{n}/" for n in range(1, count + 1)]
    site = {f"{SITE}/": links_page("/about/", "/accounts/logout/", *products)}
    site[f"{SITE}/about/"] = links_page("/")
    for path in products:
        site[f"{SITE}{path}"] = links_page("/", title=path)
    return site


def test_crawl_spends_the_budget_on_different_patterns():
    result, browser = crawl(product_site(), per_pattern=2)
    products = [url for url in browser.opened if "/products/" in url]
    assert len(products) == 2
    coverage = {c.route: c for c in result.coverage}
    assert coverage["/products/<int>/"].summary == "scanned (2 of 500)"
    assert coverage["/about/"].status == Status.SCANNED
    assert f"{SITE}/accounts/logout/" not in browser.opened
    assert coverage["/accounts/logout/"].status == Status.DENIED
    assert result.pages_checked == 4


def test_max_pages():
    result, browser = crawl(product_site(30), max_pages=2, per_pattern=50)
    assert browser.opened == [f"{SITE}/", f"{SITE}/about/"] and result.pages_checked == 2
    products = next(c for c in result.coverage if c.route == "/products/<int>/")
    assert products.summary == "skipped (30 found, page budget used up)"


def test_unvisited_patterns_come_first():
    site = product_site(5)
    site[f"{SITE}/"] = links_page(*[f"/products/{n}/" for n in range(1, 6)], "/about/")
    _, browser = crawl(site, max_pages=3, per_pattern=10)
    assert browser.opened == [f"{SITE}/", f"{SITE}/products/1/", f"{SITE}/about/"]


def test_no_crawl_opens_only_the_start_url():
    result, browser = crawl(product_site(3), crawl=False)
    assert browser.opened == [f"{SITE}/"] and browser.fetched == []
    assert result.pages_checked == 1


def test_other_origins_are_not_followed():
    site = {f"{SITE}/": links_page("https://elsewhere.test/", "http://shop.test:8080/", "/ok/")}
    site[f"{SITE}/ok/"] = links_page()
    _, browser = crawl(site)
    assert browser.opened == [f"{SITE}/", f"{SITE}/ok/"]


def test_sitemaps_from_robots_txt():
    files = {
        f"{SITE}/robots.txt": Fetched(
            f"{SITE}/robots.txt", 200, "text/plain", "Sitemap: /index.xml"
        ),
        f"{SITE}/index.xml": Fetched(
            f"{SITE}/index.xml",
            200,
            "application/xml",
            "<sitemapindex><sitemap><loc>/pages.xml</loc></sitemap></sitemapindex>",
        ),
        f"{SITE}/pages.xml": Fetched(
            f"{SITE}/pages.xml",
            200,
            "application/xml",
            "<urlset><url><loc>/hidden/</loc></url><url><loc>http://evil.test/</loc></url></urlset>",
        ),
    }
    site = {f"{SITE}/": links_page(), f"{SITE}/hidden/": links_page()}
    _, browser = crawl(site, files=files)
    assert f"{SITE}/hidden/" in browser.opened
    assert browser.fetched[:3] == [f"{SITE}/robots.txt", f"{SITE}/index.xml", f"{SITE}/pages.xml"]


def test_default_sitemap_without_robots():
    files = {
        f"{SITE}/sitemap.xml": Fetched(
            f"{SITE}/sitemap.xml",
            200,
            "application/xml",
            "<urlset><url><loc>/s/</loc></url></urlset>",
        )
    }
    _, browser = crawl({f"{SITE}/": links_page(), f"{SITE}/s/": links_page()}, files=files)
    assert f"{SITE}/s/" in browser.opened


def test_api_inventory_and_html_fragments():
    page = links_page(
        extra='<div hx-get="/fragments/cart/"></div><button hx-post="/cart/">Go</button>'
    )
    page.requests = [
        NetworkRecord("GET", f"{SITE}/api/items/", 200, "application/json; charset=utf-8", 120),
        NetworkRecord("GET", f"{SITE}/api/items/7/", 404, "application/json"),
        NetworkRecord("POST", f"{SITE}/api/track/", None),
        NetworkRecord("GET", f"{SITE}/partials/list/", 200, "text/html"),
    ]
    files = {
        f"{SITE}/fragments/cart/": Fetched(
            f"{SITE}/fragments/cart/", 200, "text/html", '<div><img src="x.png"></div>'
        ),
        f"{SITE}/partials/list/": Fetched(
            f"{SITE}/partials/list/", 200, "text/html; charset=utf-8", "<ul><li>ok</li></ul>"
        ),
    }
    result, _ = crawl({f"{SITE}/": page}, files=files)
    endpoints = {(e.method, e.pattern): e for e in result.endpoints}
    items = endpoints[("GET", "/api/items/")]
    assert items.statuses == {200} and items.content_types == {"application/json"}
    assert items.pages == {f"{SITE}/"}
    assert endpoints[("GET", "/api/items/<int>/")].statuses == {404}
    assert endpoints[("POST", "/api/track/")].failed
    assert [(a.method, a.url) for a in result.actions] == [("POST", f"{SITE}/cart/")]
    assert result.fragments == [f"{SITE}/fragments/cart/", f"{SITE}/partials/list/"]
    fragment = next(v for v in result.violations if v.url == f"{SITE}/fragments/cart/")
    assert fragment.code == "RL101" and fragment.viewport == "fragment"


def test_redirects_errors_and_login():
    site = {
        f"{SITE}/": links_page("/old/", "/broken/", "/account/", "/down/", "/file.pdf"),
        f"{SITE}/old/": FakePage(redirect=f"{SITE}/new/"),
        f"{SITE}/broken/": FakePage(status=500),
        f"{SITE}/account/": FakePage(redirect=f"{SITE}/accounts/login/?next=/account/"),
        f"{SITE}/down/": FakePage(error="net::ERR_FAILED"),
        f"{SITE}/file.pdf": FakePage(content_type="application/pdf"),
    }
    result, _ = crawl(site, login="/accounts/login/")
    coverage = {c.route: c for c in result.coverage}
    assert coverage["/old/"].redirects == {f"{SITE}/old/": f"{SITE}/new/"}
    assert coverage["/broken/"].summary == "error (HTTP 500)"
    assert coverage["/account/"].status == Status.NEEDS_LOGIN
    assert coverage["/down/"].summary == "error (net::ERR_FAILED)"
    assert coverage["/file.pdf"].summary == "skipped (not a page: application/pdf)"
    endpoint = next(e for e in result.endpoints if e.pattern == "/file.pdf")
    assert endpoint.method == "GET" and endpoint.content_types == {"application/pdf"}


def test_login_page_itself_is_not_a_login_redirect():
    site = {f"{SITE}/accounts/login/": links_page()}
    result, _ = crawl(site, start=f"{SITE}/accounts/login/", login="/accounts/login/")
    assert result.coverage[0].status == Status.SCANNED


def test_concurrency():
    result, browser = crawl(product_site(20), concurrency=3, per_pattern=3)
    assert browser.sessions == 3
    assert len(browser.opened) == len(set(browser.opened)) == 5  # /, /about/, 3 products
    assert result.pages_checked == 5


def test_worker_errors_reach_the_caller():
    def boom(url):
        raise RuntimeError("browser crashed")

    with pytest.raises(RuntimeError, match="browser crashed"):
        crawl({f"{SITE}/": links_page("/a/", "/b/"), f"{SITE}/a/": boom}, concurrency=2)


def test_delay_between_pages(monkeypatch):
    slept = []
    monkeypatch.setattr("ramplint.browser.scan.time.sleep", slept.append)
    crawl(product_site(2), delay=250)
    assert slept == [0.25] * 3


def test_progress():
    seen = []
    browser = FakeBrowser(product_site(2))
    Crawler(
        select_rules(),
        BrowserOptions(timeout=5),
        progress=lambda *args: seen.append(args),
        session_factory=browser.factory,
    ).run([f"{SITE}/"])
    assert seen[0] == (1, 1, f"{SITE}/", "desktop")
    assert seen[1] == (2, 4, f"{SITE}/about/", "desktop")
    assert [index for index, *_ in seen] == [1, 2, 3, 4]


# -- frontier with a URLconf ----------------------------------------------------


def pattern(route: str, name: str | None, line: int = 1) -> UrlPattern:
    return UrlPattern((RoutePart(route),), name, "views.x", "shop/urls.py", line)


URLCONF = UrlConf(
    module="config.urls",
    patterns=[
        pattern("", "home"),
        pattern("products/<int:pk>/", "shop:detail"),
        pattern("orders/<int:pk>/", "shop:order"),
        pattern("cart/remove-item/", "shop:remove-item"),
        pattern("accounts/sign_out/", "accounts:logout"),
    ],
)


def test_urlconf_patterns_and_coverage():
    site = {
        f"{SITE}/": links_page(
            "/products/1/", "/products/2/", "/products/3/", "/cart/remove-item/"
        ),
        f"{SITE}/products/1/": links_page(),
        f"{SITE}/products/2/": links_page(),
    }
    result, browser = crawl(site, urlconf=URLCONF, extra=start_urls(URLCONF, {}, SITE)[0])
    coverage = {c.route: c for c in result.coverage}
    assert coverage["/products/<int:pk>/"].summary == "scanned (2 of 3)"
    assert coverage["/products/<int:pk>/"].source == "shop/urls.py:1"
    assert coverage["/orders/<int:pk>/"].status == Status.NEEDS_SAMPLE
    # Denied by the pattern name, even though the URL looks harmless.
    assert coverage["/accounts/sign_out/"].status == Status.DENIED
    assert coverage["/cart/remove-item/"].status == Status.DENIED
    assert not any("sign_out" in url or "remove" in url for url in browser.opened)


def test_samples():
    urls, unknown = start_urls(URLCONF, {"shop:order": ["/orders/9/"], "nope": ["/x/"]}, SITE)
    assert f"{SITE}/orders/9/" in urls and f"{SITE}/x/" in urls
    assert unknown == ["nope"]


def test_deny_by_name_glob():
    options = BrowserOptions(deny=["shop:order"])
    frontier = Frontier(f"{SITE}/", options, URLCONF)
    assert not frontier.add(f"{SITE}/orders/1/")
    assert frontier.coverage["/orders/<int:pk>/"].status == Status.DENIED


def test_start_urls_ignore_budget_and_filters():
    options = BrowserOptions(per_pattern=1, include=["/only/*"])
    frontier = Frontier(f"{SITE}/", options)
    for n in (1, 2):
        assert frontier.add(f"{SITE}/p/{n}/", source=Source.START)
    assert not frontier.add(f"{SITE}/p/3/")  # not included
    assert [frontier.pop().url, frontier.pop().url] == [f"{SITE}/p/1/", f"{SITE}/p/2/"]
    assert frontier.pop() is None


def test_query_variations_are_one_pattern():
    frontier = Frontier(f"{SITE}/", BrowserOptions(per_pattern=1))
    frontier.add(f"{SITE}/list/?page=2")
    frontier.add(f"{SITE}/list/?page=3&sort=name")
    assert frontier.pop() is not None and frontier.pop() is None


def test_trailing_slash_variants_are_one_page():
    frontier = Frontier(f"{SITE}/", BrowserOptions())
    assert frontier.add(f"{SITE}/a/")
    assert not frontier.add(f"{SITE}/a")


def test_pattern_inference():
    inference = PatternInference()
    posts = ["hello-world", "second-post", "third-post", "post-4", "a-fifth-one"]
    for slug in posts:
        inference.observe(f"/blog/{slug}/")
    assert inference.pattern("/blog/hello-world/") == "/blog/{slug}/"
    assert inference.pattern("/blog/2026-01-02/") == "/blog/<date>/"
    for word in ("about", "contact", "team", "jobs", "press"):
        inference.observe(f"/company/{word}/")
    assert inference.pattern("/company/about/") == "/company/about/"  # words, not slugs
    assert inference.pattern("/") == "/"
    assert inference.pattern("/a/b") == "/a/b"


def test_record_without_final_url():
    frontier = Frontier(f"{SITE}/", BrowserOptions(), login_path="/login/")
    frontier.add(f"{SITE}/x/")
    candidate = frontier.pop()
    frontier.record(candidate, PageSnapshot(url=candidate.url, viewport="desktop", status=200))
    assert frontier.coverage["/x/"].status == Status.SCANNED
