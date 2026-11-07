"""``ramplint URL``: command line of the browser mode, with a fake browser."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import ramplint.browser.scan as scan_module
from ramplint.browser.options import BrowserOptions
from ramplint.browser.session import BrowserSession, BrowserUnavailable
from ramplint.browser.snapshot import ElementInfo, PageSnapshot
from ramplint.cli import EXIT_ERROR, EXIT_INTERRUPTED, EXIT_OK, EXIT_VIOLATIONS, main

HEAD = '<html lang="en" data-rl-node="1"><head><title>Page</title></head>'
GOOD = f"{HEAD}<body><main><h1>Ok</h1></main></body></html>"
BAD = f'{HEAD}<body><main><h1>Bad</h1><img src="a.png" data-rl-node="2"></main></body></html>'


def page(url: str, viewport: str, html: str = GOOD, **fields) -> PageSnapshot:
    values = {
        "final_url": url,
        "status": 200,
        "content_type": "text/html",
        "html": html,
        "elements": {
            "1": ElementInfo("1", "html", "html", (0, 0, 1, 1), True),
            "2": ElementInfo("2", "img", "body > main > img", (0, 0, 1, 1), True),
        },
        **fields,
    }
    return PageSnapshot(url=url, viewport=viewport, **values)


class FakeSession:
    """Stands in for BrowserSession.

    ``PAGES`` maps a URL to a snapshot factory, ``FILES`` a URL to what
    ``fetch()`` returns (robots.txt, sitemaps, fragments).
    """

    PAGES: dict = {}
    FILES: dict = {}
    captured: list[tuple[str, str]] = []
    fetched: list[str] = []
    options: BrowserOptions | None = None

    def __init__(self, options: BrowserOptions) -> None:
        FakeSession.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def capture(self, url, viewport, probes=()):
        FakeSession.captured.append((url, viewport.name))
        return FakeSession.PAGES.get(url, lambda u, v: page(u, v))(url, viewport.name)

    def fetch(self, url):
        FakeSession.fetched.append(url)
        return FakeSession.FILES.get(url)

    def crops(self, snapshot, boxes, padding=8):
        return [b"\xff\xd8crop" for _ in boxes]


@pytest.fixture
def fake_browser(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(scan_module, "BrowserSession", FakeSession)
    FakeSession.PAGES = {}
    FakeSession.FILES = {}
    FakeSession.captured = []
    FakeSession.fetched = []
    return FakeSession


def test_clean_page(fake_browser, capsys):
    assert main(["http://localhost:8000/"]) == EXIT_OK
    assert "All checks passed (1 page)." in capsys.readouterr().out
    assert fake_browser.captured == [("http://localhost:8000/", "desktop")]


def test_problems_and_viewports(fake_browser, capsys):
    fake_browser.PAGES["http://localhost:8000/bad/"] = lambda u, v: page(u, v, BAD)
    code = main(
        ["http://localhost:8000/", "http://localhost:8000/bad/", "--viewport", "desktop,mobile"]
    )
    assert code == EXIT_VIOLATIONS
    out = capsys.readouterr().out
    assert "http://localhost:8000/bad/ body > main > img @desktop,mobile: RL101" in out
    assert "Found 1 problem in 1 of 2 pages." in out
    assert len(fake_browser.captured) == 4


def test_options_reach_the_session(fake_browser, tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ramplint.browser]\ntimeout = 5\ndelay = 1\nwait-for = '#app'\n"
    )
    snapshots = tmp_path / "snaps"
    args = ["http://localhost:8000/", "--timeout", "7", "--headed", "--save-snapshots"]
    assert main([*args, str(snapshots)]) == EXIT_OK
    options = fake_browser.options
    assert options.timeout == 7 and options.delay == 1 and options.headed
    assert options.wait_for == "#app"
    assert (snapshots / "localhost_8000@desktop" / "snapshot.json").is_file()


def test_screenshot_format(fake_browser, tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.ramplint.browser]\nscreenshot-format = "png"\n')
    assert main(["http://localhost:8000/"]) == EXIT_OK
    assert fake_browser.options.screenshot_format == "png"
    assert main(["http://localhost:8000/", "--screenshot-format", "jpeg"]) == EXIT_OK
    assert fake_browser.options.screenshot_format == "jpeg"


def test_command_line_overrides_config(fake_browser):
    args = ["http://localhost:8000/", "--delay", "0", "--wait-for", "main", "--viewport", "mobile"]
    assert main(args) == EXIT_OK
    options = fake_browser.options
    assert options.delay == 0 and options.wait_for == "main"
    assert [v.name for v in options.viewports] == ["mobile"]


def test_json_output_file(fake_browser, tmp_path, capsys):
    fake_browser.PAGES["http://localhost:8000/"] = lambda u, v: page(u, v, BAD)
    out = tmp_path / "out" / "report.json"
    assert main(["http://localhost:8000/", "--format", "json", "-o", str(out)]) == EXIT_VIOLATIONS
    data = json.loads(out.read_text())
    assert data["violations"][0]["selector"] == "body > main > img"
    assert "json report written" in capsys.readouterr().out


def test_statistics(fake_browser, capsys):
    fake_browser.PAGES["http://localhost:8000/"] = lambda u, v: page(u, v, BAD)
    assert main(["http://localhost:8000/", "--statistics", "--exit-zero"]) == EXIT_OK
    assert "1  RL101  img-alt" in capsys.readouterr().out


def test_select_rules(fake_browser):
    fake_browser.PAGES["http://localhost:8000/"] = lambda u, v: page(u, v, BAD)
    assert main(["http://localhost:8000/", "--ignore", "img-alt"]) == EXIT_OK


def test_warnings_for_pages_that_failed(fake_browser, capsys):
    fake_browser.PAGES.update(
        {
            "http://localhost:8000/down/": lambda u, v: page(u, v, error="net::ERR_FAILED"),
            "http://localhost:8000/api/": lambda u, v: page(u, v, content_type="application/json"),
            "http://localhost:8000/404/": lambda u, v: page(u, v, status=404),
        }
    )
    urls = [f"http://localhost:8000/{p}/" for p in ("down", "api", "404")]
    assert main(urls) == EXIT_OK
    err = capsys.readouterr().err
    assert "cannot open http://localhost:8000/down/ (desktop): net::ERR_FAILED" in err
    assert "skipped http://localhost:8000/api/ (desktop): not an HTML page" in err
    assert "http://localhost:8000/404/ (desktop) returned HTTP 404" in err


def test_no_page_could_be_checked(fake_browser, capsys):
    fake_browser.PAGES["http://localhost:1/"] = lambda u, v: page(u, v, error="refused")
    assert main(["http://localhost:1/"]) == EXIT_ERROR
    assert "no page could be checked" in capsys.readouterr().err


def test_verbose_progress(fake_browser, capsys):
    assert main(["http://localhost:8000/", "-v", "--viewport", "desktop,mobile"]) == EXIT_OK
    err = capsys.readouterr().err
    assert "[1/1] http://localhost:8000/ (desktop)" in err
    assert "[1/1] http://localhost:8000/ (mobile)" in err


@pytest.mark.parametrize(
    "args, message",
    [
        (["http://localhost/", "templates"], "either URLs or files"),
        (["http://localhost/", "--list-templates"], "--list-templates does not work with URLs"),
        (["--viewport", "mobile"], "--viewport needs URLs"),
        (["templates", "--headed"], "--headed needs URLs"),
        (["http://localhost/", "--viewport", "huge"], "invalid viewport"),
        (["http://localhost/", "--timeout", "0"], "--timeout must be above 0"),
        (["http://localhost/", "--delay", "-5"], "--delay must not be negative"),
        (["http://localhost/", "--max-pages", "0"], "--max-pages must be above 0"),
        (["http://localhost/", "--per-pattern", "0"], "--per-pattern must be above 0"),
        (["--no-crawl"], "--no-crawl needs URLs to check in a browser (or base-url"),
        (["templates", "--include", "/a/*"], "--include needs URLs"),
    ],
)
def test_usage_errors(fake_browser, capsys, args, message):
    assert main(args) == EXIT_ERROR
    assert message in capsys.readouterr().err


def test_browser_unavailable(fake_browser, monkeypatch, capsys):
    class Broken(FakeSession):
        def __enter__(self):
            raise BrowserUnavailable("Chromium is not installed")

    monkeypatch.setattr(scan_module, "BrowserSession", Broken)
    assert main(["http://localhost:8000/"]) == EXIT_ERROR
    assert "ramplint: error: Chromium is not installed" in capsys.readouterr().err


def test_missing_playwright_explains_how_to_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    hint = r'pip install "ramplint\[browser\]"'
    with pytest.raises(BrowserUnavailable, match=hint), BrowserSession(BrowserOptions()):
        pass


def test_scan_result_lists_failed_pages():
    from ramplint.browser.scan import ScanResult

    result = ScanResult(
        snapshots=[page("http://a/", "desktop"), page("http://b/", "desktop", error="refused")]
    )
    assert [s.url for s in result.failed] == ["http://b/"]
    assert result.pages_checked == 1


def test_playwright_error_messages():
    from ramplint.browser.session import _first_line

    assert _first_line("Page.goto: net::ERR_FAILED at http://x/\nCall log:") == (
        "net::ERR_FAILED at http://x/"
    )
    assert _first_line("\n====\n") == "===="


def test_max_pages_caps_the_given_urls(fake_browser, capsys):
    urls = [f"http://localhost:8000/{n}/" for n in range(4)]
    assert main([*urls, "--max-pages", "2"]) == EXIT_OK
    assert [url for url, _ in fake_browser.captured] == urls[:2]
    assert "checking the first 2 of 4 URLs (--max-pages)" in capsys.readouterr().err


def test_duplicate_urls_are_opened_once(fake_browser):
    assert main(["http://localhost:8000/", "http://localhost:8000/"]) == EXIT_OK
    assert len(fake_browser.captured) == 1


def test_url_filters(fake_browser, tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ramplint.browser]\nexclude = ["/admin/*"]\ndeny = ["*/reset/*"]\n'
    )
    urls = [
        "http://localhost:8000/shop/",
        "http://localhost:8000/shop/cart/",
        "http://localhost:8000/admin/",
        "http://localhost:8000/shop/reset/",
        "http://localhost:8000/accounts/logout/",
    ]
    args = [*urls, "--include", "/shop/*", "--exclude-url", "*/cart/"]
    assert main(args) == EXIT_OK
    assert [url for url, _ in fake_browser.captured] == ["http://localhost:8000/shop/"]
    err = capsys.readouterr().err
    assert "skipped http://localhost:8000/shop/cart/: excluded by the URL filters" in err
    assert "not opening http://localhost:8000/admin/: it matches deny" in err
    assert "not opening http://localhost:8000/shop/reset/: it matches deny" in err
    assert "not opening http://localhost:8000/accounts/logout/: it matches deny" in err
    options = fake_browser.options
    assert options.exclude == ["/admin/*", "*/cart/"] and options.include == ["/shop/*"]


def test_every_url_filtered_out(fake_browser, capsys):
    assert main(["http://localhost:8000/logout/"]) == EXIT_ERROR
    assert "no URL left to check" in capsys.readouterr().err
    assert fake_browser.captured == []


def test_crawl_options_reach_the_session(fake_browser, tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ramplint.browser]\nmax-pages = 10\nper-pattern = 3\n"
    )
    assert main(["http://localhost:8000/"]) == EXIT_OK
    options = fake_browser.options
    assert (options.max_pages, options.per_pattern, options.crawl) == (10, 3, True)
    assert main(["http://localhost:8000/", "--no-crawl", "--per-pattern", "1"]) == EXIT_OK
    options = fake_browser.options
    assert (options.max_pages, options.per_pattern, options.crawl) == (10, 1, False)


def test_base_url_from_config(fake_browser, tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ramplint.browser]\nbase-url = "http://localhost:8000/"\n'
    )
    assert main(["--no-crawl"]) == EXIT_OK
    assert fake_browser.captured == [("http://localhost:8000/", "desktop")]
    # Without browser options ramplint keeps checking templates.
    fake_browser.captured = []
    main([])
    assert fake_browser.captured == []


def test_ctrl_c(fake_browser, monkeypatch, capsys):
    closed = []

    class Interrupted(FakeSession):
        def capture(self, url, viewport, probes=()):
            raise KeyboardInterrupt

        def __exit__(self, *exc):
            closed.append(exc[0])

    monkeypatch.setattr(scan_module, "BrowserSession", Interrupted)
    assert main(["http://localhost:8000/"]) == EXIT_INTERRUPTED
    assert closed == [KeyboardInterrupt]
    assert capsys.readouterr().err.strip() == "ramplint: interrupted"


def test_help_has_a_browser_group(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    browser = out[out.index("browser scan:") :]
    for flag in (
        "--viewport",
        "--timeout",
        "--delay",
        "--wait-for",
        "--headed",
        "--save-snapshots",
        "--screenshot-format",
        "--max-pages",
        "--per-pattern",
        "--include",
        "--exclude-url",
        "--no-crawl",
    ):
        assert flag in browser


def test_same_problem_on_product_pages_is_reported_once(fake_browser, capsys):
    urls = [f"http://localhost:8000/products/{n}/" for n in (1, 2, 3)]
    for url in urls:
        fake_browser.PAGES[url] = lambda u, v: page(u, v, BAD)
    assert main([*urls, "http://localhost:8000/"]) == EXIT_VIOLATIONS
    out = capsys.readouterr().out
    assert out.count("RL101") == 1
    assert "http://localhost:8000/products/1/ body > main > img: RL101" in out
    assert "(and 2 more pages)" in out
    assert "Found 1 problem in 3 of 4 pages." in out


def test_crawl_summary_and_coverage(fake_browser, capsys):
    fake_browser.PAGES["http://localhost:8000/"] = lambda u, v: page(
        u, v, GOOD.replace("<h1>Ok</h1>", '<h1>Ok</h1><a href="/a/">A</a>')
    )
    assert main(["http://localhost:8000/", "-v"]) == EXIT_OK
    err = capsys.readouterr().err
    assert "ramplint: crawled 2 pages of 2 URL patterns\n" in err
    assert "ramplint:   /a/  scanned (1 of 1)" in err
    assert [url for url, _ in fake_browser.captured] == [
        "http://localhost:8000/",
        "http://localhost:8000/a/",
    ]


def test_no_crawl_has_no_summary(fake_browser, capsys):
    assert main(["http://localhost:8000/", "--no-crawl"]) == EXIT_OK
    assert "crawled" not in capsys.readouterr().err
    assert fake_browser.fetched == []


def test_django_project_urls_and_samples(fake_browser, tmp_path, capsys):
    files = {
        "manage.py": "",
        "settings.py": "ROOT_URLCONF = 'urls'\nLOGIN_URL = 'login'\n",
        "urls.py": (
            "from django.urls import include, path\n"
            "urlpatterns = [\n"
            "    path('', v, name='home'),\n"
            "    path('about/', v, name='about'),\n"
            "    path('items/<int:pk>/', v, name='item'),\n"
            "    path('login/', v, name='login'),\n"
            "    path('x/', include('nowhere.urls')),\n"
            "]\n"
        ),
        "pyproject.toml": (
            '[tool.ramplint.browser.samples]\n"item" = ["/items/7/"]\n"ghost" = ["/g/"]\n'
        ),
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    assert main(["http://localhost:8000/", "-v"]) == EXIT_OK
    opened = [url for url, _ in fake_browser.captured]
    assert opened[0] == "http://localhost:8000/"
    assert set(opened) == {
        "http://localhost:8000/",
        "http://localhost:8000/about/",
        "http://localhost:8000/login/",
        "http://localhost:8000/items/7/",
        "http://localhost:8000/g/",
    }
    err = capsys.readouterr().err
    assert "sample 'ghost' matches no URL pattern name" in err
    assert "ramplint: URL patterns from urls" in err
    assert "not read: urls.py:7: include('nowhere.urls') is not part of the project" in err


def test_login_path():
    from ramplint.browser.command import DEFAULT_LOGIN_PATH, login_path
    from ramplint.project.discovery import Project
    from ramplint.project.settings import Settings
    from ramplint.project.urls import RoutePart, UrlConf, UrlPattern

    conf = UrlConf("u", [UrlPattern((RoutePart("in/"),), "account_login", None, "u.py", 1)])

    def project(value):
        return Project(root=Path("."), settings=Settings("s", {"LOGIN_URL": value}))

    assert login_path(None, None) == DEFAULT_LOGIN_PATH
    assert login_path(project("/signin/"), conf) == "/signin/"
    assert login_path(project("account_login"), conf) == "/in/"
    assert login_path(project("unknown"), conf) == DEFAULT_LOGIN_PATH
    assert login_path(project("account_login"), None) == DEFAULT_LOGIN_PATH


def test_coverage_summary_wording():
    from ramplint.browser.command import coverage_summary
    from ramplint.browser.frontier import Coverage

    scanned = Coverage("/", scanned=["u"], found={"u"})
    sample = Coverage("/p/<int:pk>/", has_parameters=True)
    login = Coverage("/me/", found={"m"}, login_required=["m"])
    failed = Coverage("/x/", found={"x"}, results={"x": "HTTP 500"})
    skipped = Coverage("/y/", found={"y"})
    assert coverage_summary([scanned], 1) == "crawled 1 page of 1 URL pattern"
    assert coverage_summary([scanned, sample, sample, login, failed, skipped], 3) == (
        "crawled 3 pages of 1 URL pattern; 2 need a sample URL, 1 needs login, "
        "1 failed, 1 was skipped"
    )


def test_concurrency_option(fake_browser):
    assert main(["http://localhost:8000/", "--concurrency", "2", "--no-crawl"]) == EXIT_OK
    assert fake_browser.options.concurrency == 2
    assert main(["http://localhost:8000/", "--concurrency", "0"]) == EXIT_ERROR


def test_save_auth(fake_browser, monkeypatch, tmp_path, capsys):
    import ramplint.browser.command as command

    saved = []
    monkeypatch.setattr(
        command, "save_auth", lambda url, path, options: saved.append((url, path, options.headed))
    )
    target = tmp_path / "admin.json"
    assert main(["http://localhost:8000/login/", "--save-auth", str(target)]) == EXIT_OK
    assert saved == [("http://localhost:8000/login/", target, True)]
    assert f"saved the session to {target}" in capsys.readouterr().err
    assert main(["http://a/", "http://b/", "--save-auth", str(target)]) == EXIT_ERROR
    assert "exactly one URL" in capsys.readouterr().err


def test_save_auth_without_browser(fake_browser, monkeypatch, tmp_path, capsys):
    import ramplint.browser.command as command

    def broken(url, path, options):
        raise BrowserUnavailable("Chromium is not installed")

    monkeypatch.setattr(command, "save_auth", broken)
    assert main(["http://x/login/", "--save-auth", str(tmp_path / "a.json")]) == EXIT_ERROR
    assert "Chromium is not installed" in capsys.readouterr().err


def test_auth_files_must_exist(fake_browser, tmp_path, capsys):
    assert main(["http://x/", "--auth", str(tmp_path / "nope.json")]) == EXIT_ERROR
    assert "does not exist (create it with --save-auth)" in capsys.readouterr().err


def test_scan_per_role(fake_browser, tmp_path, monkeypatch, capsys):
    import ramplint.browser.command as command

    monkeypatch.setattr(command, "unprotected_secret", lambda path: path.stem == "admin")
    for name in ("admin", "shop"):
        (tmp_path / f"{name}.json").write_text("{}")
    fake_browser.PAGES["http://localhost:8000/"] = lambda u, v: page(u, v, BAD)
    args = ["http://localhost:8000/", "--no-crawl"]
    code = main(
        [*args, "--auth", str(tmp_path / "admin.json"), "--auth", str(tmp_path / "shop.json")]
    )
    assert code == EXIT_VIOLATIONS
    captured = capsys.readouterr()
    assert "[as admin,shop]: RL101" in captured.out
    assert "scanning as admin" in captured.err and "scanning as shop" in captured.err
    assert "admin.json holds your session cookies and git does not ignore it" in captured.err
    assert fake_browser.options.storage_state == str(tmp_path / "shop.json")
