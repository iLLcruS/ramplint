"""``ramplint.testing``: checks of rendered responses in a test suite."""

from __future__ import annotations

import unittest

import pytest

from ramplint import testing
from ramplint.testing import (
    AccessibilityError,
    AccessibilityTestMixin,
    assert_accessible,
    check_html,
    check_response,
)

PAGE = (
    '<!doctype html>\n<html lang="en">\n<head><title>Shop</title></head>\n'
    "<body><main>\n{body}\n</main></body>\n</html>\n"
)
BAD = PAGE.format(body='<img src="a.png">')
GOOD = PAGE.format(body='<img src="a.png" alt="Logo">')


class Request:
    path = "/products/"


class Response:
    """Enough of ``django.http.HttpResponse`` for the checks."""

    def __init__(self, html: str, content_type: str = "text/html; charset=utf-8") -> None:
        self.content = html.encode("utf-8")
        self.charset = "utf-8"
        self.headers = {"Content-Type": content_type}
        self.wsgi_request = Request()
        self.streaming = False


@pytest.fixture(autouse=True)
def no_project_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    testing._project_config.cache_clear()
    yield
    testing._project_config.cache_clear()


def test_check_html_finds_problems():
    assert [v.code for v in check_html(BAD)] == ["RL101"]
    assert check_html(GOOD) == []


def test_check_response_uses_the_request_path():
    (violation,) = check_response(Response(BAD))
    assert violation.path == "/products/"
    assert violation.line == 5


def test_non_html_responses_are_skipped():
    assert check_response(Response('{"a": 1}', "application/json")) == []


def test_response_without_headers_attribute():
    class Old:
        content = BAD.encode()
        charset = None
        request = {"PATH_INFO": "/old/"}

        def get(self, name):
            return "text/html"

    (violation,) = check_response(Old())
    assert violation.path == "/old/"


def test_streaming_response_is_refused():
    response = Response(BAD)
    response.streaming = True
    with pytest.raises(ValueError, match="streaming"):
        check_response(response)


def test_assert_accessible_message_lists_problems():
    with pytest.raises(AccessibilityError) as info:
        assert_accessible(Response(BAD))
    message = str(info.value)
    assert message.startswith("1 accessibility problem in /products/:")
    assert "5:1: RL101" in message
    assert [v.code for v in info.value.violations] == ["RL101"]


def test_assert_accessible_passes_and_accepts_strings_and_bytes():
    assert_accessible(Response(GOOD))
    assert_accessible(GOOD)
    with pytest.raises(AccessibilityError, match="in the HTML"):
        assert_accessible(BAD.encode())


def test_select_and_ignore():
    assert_accessible(BAD, ignore=["img-alt"])
    assert_accessible(BAD, select=["RL5"])
    with pytest.raises(ValueError, match="unknown rule"):
        assert_accessible(BAD, select=["RL999"])


def test_pyproject_ignore_applies(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.ramplint]\nignore = ["RL101"]\n')
    testing._project_config.cache_clear()
    assert_accessible(BAD)


def test_broken_pyproject_is_ignored(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.ramplint\n")
    testing._project_config.cache_clear()
    assert [v.code for v in check_html(BAD)] == ["RL101"]


def test_template_locations_from_the_source_map():
    html = PAGE.format(body='<img src="a.png" data-rl-src="catalog/list.html:4:9">')
    (violation,) = check_html(html)
    assert violation.template == "catalog/list.html:4:9"
    with pytest.raises(AccessibilityError, match=r"\(catalog/list.html:4:9\)"):
        assert_accessible(html)


def test_browser_and_forms_rules_never_run():
    codes = {rule.code for rule in testing._rules(None, None)}
    assert "RL801" not in codes  # color-contrast needs a browser
    assert "RL405" not in codes  # forms.py rule
    assert "RL101" in codes


class MixinTests(AccessibilityTestMixin, unittest.TestCase):
    def test_assert_accessible(self):
        self.assertAccessible(GOOD)
        with self.assertRaises(AssertionError):
            self.assertAccessible(Response(BAD))


def test_mixin_runs_in_unittest():
    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(MixinTests).run(result)
    assert result.wasSuccessful()
