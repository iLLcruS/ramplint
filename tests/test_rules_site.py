"""Site-wide rules (RL901-RL904) on fixture sites, crawled with a fake browser."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from fakes import FakeBrowser, FakePage

from ramplint import lint_source
from ramplint.browser.checks import check_site
from ramplint.browser.options import BrowserOptions
from ramplint.browser.scan import Crawler
from ramplint.browser.snapshot import PageSnapshot
from ramplint.rules import select_rules

SITES = Path(__file__).parent / "sites" / "sitewide"
BASE = "http://shop.test"
#: URL of each fixture file.
ROUTES = {
    "index.html": "/",
    "shop.html": "/shop/",
    "about.html": "/about/",
    "contact.html": "/contact/",
}


def site(name: str) -> dict[str, FakePage]:
    return {
        f"{BASE}{route}": FakePage(html=(SITES / name / file).read_text())
        for file, route in ROUTES.items()
    }


def crawl(name: str) -> list:
    browser = FakeBrowser(site(name))
    crawler = Crawler(
        select_rules(["RL9"]), BrowserOptions(timeout=5), session_factory=browser.factory
    )
    return crawler.run([f"{BASE}/"]).violations


def snapshots(name: str) -> list[PageSnapshot]:
    return [
        PageSnapshot(
            url=url,
            viewport="desktop",
            status=200,
            content_type="text/html",
            title=page.html.split("<title>")[1].split("</title>")[0],
            html=page.html,
        )
        for url, page in site(name).items()
    ]


def test_good_site_has_no_problems():
    assert crawl("good") == []


def test_bad_site():
    found = {v.code: v for v in crawl("bad")}
    assert sorted(found) == ["RL901", "RL902", "RL903", "RL904"]

    title = found["RL901"]
    assert title.path == f"{BASE}/" and title.pages == (f"{BASE}/", f"{BASE}/shop/")
    assert title.message.startswith('2 different pages are all titled "Shoply"')

    navigation = found["RL902"]
    assert navigation.path == f"{BASE}/about/"
    assert navigation.message.startswith(
        'Navigation "main" lists the same links in a different order'
    )
    assert len(navigation.pages) == 4

    identification = found["RL903"]
    assert identification.message.startswith(f"The link to {BASE}/ in the header is named")
    assert '"Shoply" (3 pages), "Home page" (1 page)' in identification.message
    assert identification.path == f"{BASE}/about/"

    bypass = found["RL904"]
    assert bypass.pages == (f"{BASE}/", f"{BASE}/shop/")
    assert "no skip link and no <main>" in bypass.message


def test_icon_buttons_with_different_names():
    violations = check_site(snapshots("bad"), select_rules(["RL903"]))
    button = next(v for v in violations if "button" in v.message)
    assert button.message == (
        "The button with icon /icons.svg#search is named differently on different pages: "
        '"Find" (1 page), "Search" (1 page); use the same name everywhere'
    )
    assert button.pages == (f"{BASE}/", f"{BASE}/shop/")


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_results_do_not_depend_on_crawl_order(seed):
    pages = snapshots("bad")
    expected = check_site(pages, select_rules(["RL9"]))
    random.Random(seed).shuffle(pages)
    shuffled = check_site(pages, select_rules(["RL9"]))
    assert [(v.code, v.path, v.message, v.pages) for v in shuffled] == [
        (v.code, v.path, v.message, v.pages) for v in expected
    ]


def test_one_page_is_not_a_site():
    assert check_site(snapshots("bad")[:1], select_rules(["RL9"])) == []


def test_site_rules_do_nothing_in_template_mode():
    assert lint_source("<title>x</title>", rules=select_rules(["RL9"])) == []
