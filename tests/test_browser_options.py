"""Browser mode options, config, snapshots on disk and reporters - no browser needed."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ramplint.browser.options import (
    DEFAULT_DENY,
    BrowserOptions,
    Viewport,
    is_url,
    parse_viewport,
    url_matches,
)
from ramplint.browser.snapshot import ElementInfo, PageSnapshot, image_extension, padded_box
from ramplint.config import ConfigError, load_config
from ramplint.linter import Violation
from ramplint.reporters import REPORTERS, browser_report, report_context, summary_line


@pytest.mark.parametrize(
    "value, expected",
    [
        ("desktop", Viewport("desktop", 1280, 800, False)),
        ("Mobile", Viewport("mobile", 390, 844, True)),
        ("tablet", Viewport("tablet", 768, 1024, True)),
        ("320x640", Viewport("320x640", 320, 640, True)),
        ("1920x1080", Viewport("1920x1080", 1920, 1080, False)),
    ],
)
def test_parse_viewport(value, expected):
    assert parse_viewport(value) == expected


@pytest.mark.parametrize("value", ["huge", "100", "x300", "1x1"])
def test_invalid_viewport(value):
    with pytest.raises(ValueError, match="invalid viewport"):
        parse_viewport(value)


def test_is_url():
    assert is_url("http://localhost:8000") and is_url("HTTPS://example.com/")
    assert not is_url("templates/") and not is_url("ftp://x")


@pytest.mark.parametrize(
    "url, pattern, expected",
    [
        ("http://x/admin/users/", "/admin/*", True),
        ("http://x/admin", "/admin/*", False),
        ("http://x/", "/", True),
        ("http://x", "/", True),
        ("http://x/list/?page=2", "*?page=*", True),
        ("http://x/list/", "*?page=*", False),
        ("https://shop.example.com/a/", "https://shop.example.com/*", True),
        ("https://blog.example.com/a/", "https://shop.example.com/*", False),
        ("http://x/Admin/", "/admin/*", False),
    ],
)
def test_url_matches(url, pattern, expected):
    assert url_matches(url, [pattern]) is expected


def test_url_filters():
    options = BrowserOptions(include=["/shop/*"], exclude=["*/cart/"])
    assert options.allowed("http://x/shop/item/")
    assert not options.allowed("http://x/shop/cart/")
    assert not options.allowed("http://x/blog/")
    assert not options.allowed("http://x/shop/logout/")
    assert BrowserOptions().allowed("http://x/anything/")
    for url in ("http://x/accounts/logout/", "http://x/sign-out", "http://x/a/signout/?next=/"):
        assert BrowserOptions().denied(url)


def write_config(tmp_path, body: str):
    path = tmp_path / "pyproject.toml"
    path.write_text(f"[tool.ramplint.browser]\n{body}\n")
    return path


def test_browser_config(tmp_path):
    path = write_config(
        tmp_path,
        'viewports = ["desktop", "320x640"]\ntimeout = 10\ndelay = 250\nheaded = true\n'
        'wait_for = "#app"',
    )
    config = load_config(path)
    assert config.browser == {
        "viewports": [parse_viewport("desktop"), parse_viewport("320x640")],
        "timeout": 10.0,
        "delay": 250,
        "headed": True,
        "wait_for": "#app",
    }


@pytest.mark.parametrize(
    "body, message",
    [
        ("viewports = []", "non-empty list"),
        ('viewports = "desktop"', "non-empty list"),
        ('viewports = ["giant"]', "invalid viewport"),
        ("timeout = 0", "seconds above 0"),
        ("timeout = true", "seconds above 0"),
        ("delay = -1", "milliseconds"),
        ("delay = 1.5", "milliseconds"),
        ('headed = "yes"', "true or false"),
        ('wait-for = ""', "CSS selector"),
        ('base-url = "localhost:8000"', "http:// or https:// URL"),
        ("base-url = 8000", "http:// or https:// URL"),
        ("max-pages = 0", "whole number above 0"),
        ("per-pattern = 1.5", "whole number above 0"),
        ("max-pages = true", "whole number above 0"),
        ('crawl = "no"', "true or false"),
        ('include = "/a/*"', "list of URL patterns"),
        ('exclude = [""]', "list of URL patterns"),
        ("deny = [1]", "list of URL patterns"),
        ("follow = true", "unknown option follow"),
        ('screenshot-format = "gif"', "one of: jpeg, png"),
    ],
)
def test_invalid_browser_config(tmp_path, body, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(tmp_path, body))


def test_browser_crawl_config(tmp_path):
    path = write_config(
        tmp_path,
        'base-url = "http://localhost:8000/"\nmax-pages = 200\nper_pattern = 1\ncrawl = false\n'
        'include = ["/shop/*"]\nexclude = ["/admin/*"]\ndeny = ["*/reset/*"]',
    )
    browser = load_config(path).browser
    assert browser == {
        "base_url": "http://localhost:8000/",
        "max_pages": 200,
        "per_pattern": 1,
        "crawl": False,
        "include": ["/shop/*"],
        "exclude": ["/admin/*"],
        "deny": [*DEFAULT_DENY, "*/reset/*"],
    }
    png = load_config(write_config(tmp_path, 'screenshot-format = "PNG"')).browser
    assert png == {"screenshot_format": "png"}
    options = BrowserOptions(**browser)
    assert options.denied("http://x/accounts/logout/") and options.denied("http://x/reset/1/")


def test_browser_config_must_be_a_table(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.ramplint]\nbrowser = "yes"\n')
    with pytest.raises(ConfigError, match="must be a table"):
        load_config(path)


def make_snapshot() -> PageSnapshot:
    return PageSnapshot(
        url="http://localhost:8000/a/?q=1",
        viewport="mobile",
        status=200,
        content_type="text/html",
        title="A",
        html="<html><body><p>Hi</p></body></html>",
        elements={
            "1": ElementInfo("1", "html", "html", (0, 0, 390, 800), True),
            "2": ElementInfo(
                "2", "p", "body > p", (8, 8, 100, 20), True, {"color": "red"}, "paragraph", "Hi"
            ),
        },
        page_size=(390, 800),
        console_errors=["boom"],
        screenshot=b"\xff\xd8viewport",
        full_screenshot=b"\xff\xd8full",
    )


def test_snapshot_save_and_load(tmp_path):
    original = make_snapshot()
    folder = original.save(tmp_path / original.folder_name())
    assert folder.name == "localhost_8000_a_q_1@mobile"
    loaded = PageSnapshot.load(folder)
    assert loaded == original
    assert loaded.screenshot == b"\xff\xd8viewport"


def test_snapshot_without_screenshots(tmp_path):
    original = make_snapshot()
    original.screenshot = original.full_screenshot = None
    (tmp_path / "s").mkdir()
    original.save(tmp_path / "s")
    (tmp_path / "s" / "page.html").unlink()
    loaded = PageSnapshot.load(tmp_path / "s")
    assert loaded.screenshot is None and loaded.html == ""


def test_png_snapshot_save_and_load(tmp_path):
    original = make_snapshot()
    original.screenshot = b"\x89PNGviewport"
    original.full_screenshot = b"\x89PNGfull"
    folder = original.save(tmp_path / "png")
    assert sorted(p.name for p in folder.iterdir()) == [
        "full.png",
        "page.html",
        "screenshot.png",
        "snapshot.json",
    ]
    assert PageSnapshot.load(folder) == original


def test_image_extension():
    assert image_extension(b"\x89PNG\r\n") == "png"
    assert image_extension(b"\xff\xd8\xff") == "jpg"


@pytest.mark.parametrize(
    "box, expected",
    [
        ((10, 20, 30, 40), (2, 12, 46, 56)),
        ((2, 3, 10, 10), (0, 0, 20, 21)),  # clipped at the top left
        ((90, 90, 20, 20), (82, 82, 18, 18)),  # clipped at the bottom right
        ((10, 10, 0, 5), None),  # no size
        ((200, 200, 10, 10), None),  # outside the page
    ],
)
def test_padded_box(box, expected):
    assert padded_box(box, 8, (100, 100)) == expected


def test_snapshot_schema_is_checked():
    with pytest.raises(ValueError, match="schema"):
        PageSnapshot.from_dict({"schema": 99, "url": "u", "viewport": "desktop"})


def test_snapshot_state():
    page = make_snapshot()
    assert page.ok and page.is_html
    page.content_type = "application/xhtml+xml; charset=utf-8"
    assert page.is_html
    page.content_type = "application/pdf"
    assert not page.is_html
    page.error = "timed out"
    assert not page.ok
    assert PageSnapshot(url="http://x/", viewport="desktop").folder_name() == "x@desktop"
    assert PageSnapshot(url="http://", viewport="desktop").folder_name() == "page@desktop"


# -- reporters ------------------------------------------------------------

BROWSER_VIOLATIONS = [
    Violation(
        "http://localhost:8000/",
        12,
        5,
        "RL501",
        "button-name",
        "<button> has no accessible name",
        url="http://localhost:8000/",
        selector="body > main > button",
        viewport="desktop,mobile",
        bbox=(1.0, 2.0, 3.0, 4.0),
    ),
    Violation(
        "http://localhost:8000/",
        14,
        1,
        "RL101",
        "img-alt",
        "<img> is missing an alt",
        url="http://localhost:8000/",
        selector="#logo",
        viewport="mobile",
    ),
]


def render(fmt: str, viewports=("desktop", "mobile")) -> str:
    out = io.StringIO()
    with browser_report(viewports):
        REPORTERS[fmt].write(BROWSER_VIOLATIONS, 3, out, False)
    return out.getvalue()


def test_report_context_is_restored():
    with browser_report(["desktop"]) as context:
        assert report_context() is context and context.browser
        assert summary_line([], 1) == "All checks passed (1 page)."
        assert summary_line(BROWSER_VIOLATIONS, 3) == "Found 2 problems in 1 of 3 pages."
    assert not report_context().browser
    assert summary_line([], 2) == "All checks passed (2 files)."


def test_text_report():
    text = render("text")
    assert (
        "http://localhost:8000/ body > main > button @desktop,mobile: RL501 "
        "<button> has no accessible name [button-name]"
    ) in text
    assert "http://localhost:8000/ #logo @mobile: RL101" in text
    assert "Found 2 problems in 1 of 3 pages." in text


def test_text_report_one_viewport_hides_it():
    assert "@" not in render("text", viewports=("desktop",)).split("Found")[0].replace(
        "http://", ""
    )


def test_json_report():
    data = json.loads(render("json"))
    first = data["violations"][0]
    assert first["url"] == "http://localhost:8000/"
    assert first["selector"] == "body > main > button"
    assert first["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert "bbox" not in data["violations"][1]


def test_github_report_has_no_file_for_pages():
    lines = render("github").splitlines()
    assert lines[0].startswith("::error title=RL501 button-name::http://localhost:8000/ ")
    assert "file=" not in lines[0]


def test_sarif_report():
    import jsonschema

    schema_file = Path(__file__).parent / "data" / "sarif-schema-2.1.0.json"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    data = json.loads(render("sarif"))
    jsonschema.validate(data, schema)
    result = data["runs"][0]["results"][0]
    location = result["locations"][0]
    assert location["physicalLocation"]["artifactLocation"]["uri"] == "http://localhost:8000/"
    assert location["logicalLocations"][0]["fullyQualifiedName"] == "body > main > button"
    assert result["properties"]["viewports"] == ["desktop", "mobile"]


def test_sarif_report_without_selector():
    out = io.StringIO()
    v = Violation("http://x/", 1, 1, "RL601", "html-lang", "m", url="http://x/")
    REPORTERS["sarif"].write([v], 1, out, False)
    result = json.loads(out.getvalue())["runs"][0]["results"][0]
    assert "logicalLocations" not in result["locations"][0]
    assert result["properties"] == {"url": "http://x/"}


def test_html_report():
    html = render("html")
    assert "2 accessibility problems in 1 page" in html
    assert "Pages checked" in html and "Templates" not in html
    assert '<th scope="col">Viewport</th>' in html
    assert '<code class="selector">body &gt; main &gt; button</code>' in html
    assert "desktop, mobile" in html


MERGED = Violation(
    "http://x/products/1/",
    3,
    1,
    "RL101",
    "img-alt",
    "<img> is missing an alt",
    url="http://x/products/1/",
    selector="#logo",
    viewport="desktop",
    template="catalog/product.html:4",
    pages=("http://x/products/1/", "http://x/products/2/", "http://x/products/3/"),
)
ONE_PAGE = Violation(
    "http://x/", 1, 1, "RL601", "html-lang", "no lang", url="http://x/", pages=("http://x/",)
)


def render_merged(fmt: str) -> str:
    out = io.StringIO()
    with browser_report(["desktop"]):
        REPORTERS[fmt].write([MERGED, ONE_PAGE], 5, out, False)
    return out.getvalue()


def test_problem_on_several_pages():
    text = render_merged("text")
    assert (
        "http://x/products/1/ #logo: RL101 <img> is missing an alt [img-alt] (and 2 more pages)"
        in text
    )
    assert "[html-lang]\n" in text  # nothing added for one page
    assert "Found 2 problems in 4 of 5 pages." in text
    github = render_merged("github")
    assert "is missing an alt (and 2 more pages)" in github
    data = json.loads(render_merged("json"))
    assert data["violations"][0]["pages"][2] == "http://x/products/3/"
    properties = json.loads(render_merged("sarif"))["runs"][0]["results"][0]["properties"]
    assert len(properties["pages"]) == 3 and properties["template"] == "catalog/product.html:4"
    html = render_merged("html")
    assert 'Also on: <a href="http://x/products/2/">http://x/products/2/</a>, ' in html
    assert "<dt>Pages with problems</dt><dd>4</dd>" in html
    assert "2 accessibility problems in 4 pages" in html
    assert summary_line([MERGED], 3) == "Found 1 problem in 3 of 3 files."


def test_html_report_passes_ramplint(tmp_path):
    from ramplint import lint_file

    page = tmp_path / "report.html"
    page.write_text(render("html"), encoding="utf-8")
    assert lint_file(page) == []


def test_no_pages_html_report():
    out = io.StringIO()
    with browser_report(["desktop"]):
        REPORTERS["html"].write([], 2, out, False)
    assert "Every checked page passed" in out.getvalue()
