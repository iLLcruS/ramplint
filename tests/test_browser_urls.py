"""URL patterns used to merge the same problem on pages of one kind."""

from __future__ import annotations

import pytest

from ramplint.browser.urls import url_pattern


@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://x/", "http://x/"),
        ("http://x", "http://x/"),
        ("http://x/products/42/", "http://x/products/<int>/"),
        ("http://x/products/42", "http://x/products/<int>"),
        ("http://x/shop/7/items/9/", "http://x/shop/<int>/items/<int>/"),
        (
            "http://x/o/3f2b8c1e-9d4a-4b6e-8f1a-2c3d4e5f6a7b/",
            "http://x/o/<uuid>/",
        ),
        ("http://x/blog/2026-11-07/", "http://x/blog/<date>/"),
        ("http://x/reset/9f86d081884c7d659a2feaa0c55ad015/", "http://x/reset/<hash>/"),
        ("http://x/products/blue-shirt/", "http://x/products/blue-shirt/"),
        ("http://x/about/", "http://x/about/"),
        ("http://x/deadbeefdeadbeef/", "http://x/deadbeefdeadbeef/"),  # no digit: a word
        ("http://x/list/?page=2&sort=name", "http://x/list/?page=&sort="),
        ("http://x/list/?sort=a&page=3", "http://x/list/?page=&sort="),
        ("https://x:8000/v2/a/", "https://x:8000/v2/a/"),
    ],
)
def test_url_pattern(url, expected):
    assert url_pattern(url) == expected


def test_different_hosts_differ():
    assert url_pattern("http://a/1/") != url_pattern("http://b/1/")
