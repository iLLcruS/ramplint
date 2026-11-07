"""Browser report folder, scan.json and --baseline, with a fake browser."""

from __future__ import annotations

import json

import pytest
from test_browser_cli import BAD, GOOD, page

from ramplint import lint_file
from ramplint.browser.baseline import (
    EXISTING,
    NEW,
    BaselineError,
    compare,
    fingerprint,
    load_baseline,
)
from ramplint.cli import EXIT_ERROR, EXIT_OK, EXIT_VIOLATIONS, main
from ramplint.linter import Violation

pytest_plugins = ["test_browser_cli"]

HOME = "http://localhost:8000/"


def shot(url, viewport, html=BAD):
    snapshot = page(url, viewport, html, page_size=(1280, 900), title=f"Shop {url}")
    snapshot.full_screenshot = b"\xff\xd8full"
    snapshot.elements["2"].box = (10, 20, 100, 50)
    return snapshot


@pytest.fixture
def site(fake_browser):
    fake_browser.PAGES[HOME] = lambda u, v: shot(
        u, v, BAD.replace("<h1>Bad</h1>", '<h1>Bad</h1><a href="/about/">About</a>')
    )
    fake_browser.PAGES[f"{HOME}about/"] = lambda u, v: shot(u, v, GOOD)
    return fake_browser


def test_report_folder(site, tmp_path, capsys):
    folder = tmp_path / "a11y"
    assert main([HOME, "--format", "html", "-o", f"{folder}/"]) == EXIT_VIOLATIONS
    assert f"html report written to {folder / 'index.html'}" in capsys.readouterr().out
    names = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    assert names == [
        "api.html",
        "index.html",
        "pages/localhost_8000@desktop.html",
        "pages/localhost_8000_about@desktop.html",
        "scan.json",
        "screenshots/localhost_8000@desktop-1.jpg",
        "screenshots/localhost_8000@desktop.jpg",
        "screenshots/localhost_8000_about@desktop.jpg",
        "site-map.html",
    ]
    index = (folder / "index.html").read_text()
    assert 'src="screenshots/localhost_8000@desktop-1.jpg"' in index
    assert 'href="pages/localhost_8000@desktop.html"' in index
    assert '<a href="site-map.html">Site map</a>' in index
    page_report = (folder / "pages" / "localhost_8000@desktop.html").read_text()
    assert 'id="marker-1" style="left:0.781%;top:2.222%;width:7.812%;height:5.556%"' in page_report
    assert '<a href="#marker-1">Marker 1</a>' in page_report
    assert 'src="../screenshots/localhost_8000@desktop.jpg"' in page_report
    site_map = (folder / "site-map.html").read_text()
    assert "scanned (1 of 1)" in site_map
    # Every page of the report passes ramplint itself.
    for html in folder.rglob("*.html"):
        assert lint_file(html) == [], html


def test_scan_json(site, tmp_path):
    folder = tmp_path / "a11y"
    main([HOME, "--format", "html", "-o", str(folder)])
    data = json.loads((folder / "scan.json").read_text())
    assert data["schema"] == 1 and data["tool"]["name"] == "ramplint"
    assert data["start_urls"] == [HOME] and data["viewports"] == ["desktop"]
    assert [p["url"] for p in data["pages"]] == [HOME, f"{HOME}about/"]
    (finding,) = data["violations"]
    assert finding["code"] == "RL101" and finding["url"] == HOME
    assert finding["selector"] == "body > main > img" and finding["viewport"] == "desktop"
    assert len(finding["fingerprint"]) == 16
    assert finding["screenshot"] == "screenshots/localhost_8000@desktop-1.jpg"
    assert {c["route"] for c in data["coverage"]} == {"/", "/about/"}
    assert data["endpoints"] == [] and data["manual_checks"] == []


def test_embedded_screenshots(site, tmp_path, monkeypatch, capsys):
    import ramplint.browser.command as command

    monkeypatch.setattr(command, "EMBED_WARNING_BYTES", 10)
    target = tmp_path / "report.html"
    args = [HOME, "--format", "html", "-o", str(target), "--embed-screenshots"]
    assert main(args) == EXIT_VIOLATIONS
    html = target.read_text()
    assert 'src="data:image/jpeg;base64,/9hjcm9w"' in html
    assert "pages/" not in html
    assert "keeps the screenshots as separate files" in capsys.readouterr().err
    assert lint_file(target) == []
    assert main([HOME, "--format", "html", "-o", str(tmp_path / "x"), "--embed-screenshots"]) == (
        EXIT_ERROR
    )
    assert "--embed-screenshots needs --format html -o FILE.html" in capsys.readouterr().err


def test_html_file_without_screenshots(site, tmp_path):
    target = tmp_path / "report.html"
    main([HOME, "--format", "html", "-o", str(target)])
    assert target.is_file() and not (tmp_path / "screenshots").exists()


def test_report_folder_that_cannot_be_written(site, tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("")
    assert main([HOME, "--format", "html", "-o", f"{blocker}/sub/"]) == EXIT_ERROR
    assert "cannot write the report to" in capsys.readouterr().err


# -- baseline -------------------------------------------------------------------------


def finding(**fields) -> Violation:
    values = {
        "path": HOME,
        "line": 3,
        "col": 5,
        "code": "RL801",
        "name": "color-contrast",
        "message": "Contrast of 2.32:1 is below 4.5:1 for text (#aaaaaa on #ffffff)",
        "url": "http://localhost:8000/products/7/",
        "selector": "main > p:nth-of-type(2)",
        **fields,
    }
    return Violation(**values)


def test_fingerprint_survives_unrelated_changes():
    base = fingerprint(finding())
    assert fingerprint(finding(line=40, col=1)) == base  # moved in the page
    assert fingerprint(finding(selector="main > p:nth-of-type(5)")) == base
    assert fingerprint(finding(url="http://ci.example:9000/products/9/")) == base
    assert fingerprint(finding(message=finding().message.replace("2.32", "2.4"))) == base
    assert fingerprint(finding(code="RL101")) != base
    assert fingerprint(finding(url="http://localhost:8000/about/")) != base
    on_template = fingerprint(finding(template="shop/product.html:12:5"))
    assert fingerprint(finding(template="shop/product.html:30:9")) == on_template
    assert fingerprint(finding(template="shop/list.html:12:5")) != on_template
    static = Violation("shop/a.html", 1, 1, "RL101", "img-alt", "m")
    assert fingerprint(static) != fingerprint(
        Violation("shop/b.html", 1, 1, "RL101", "img-alt", "m")
    )


def test_compare():
    old = [
        {"fingerprint": fingerprint(finding()), "code": "RL801"},
        {"fingerprint": fingerprint(finding(code="RL101")), "code": "RL101", "message": "gone"},
    ]
    comparison = compare([finding(), finding(), finding(code="RL502")], old)
    assert [v.baseline for v in comparison.violations] == [EXISTING, NEW, NEW]
    assert len(comparison.new) == 2 and len(comparison.existing) == 1
    assert comparison.fixed == [old[1]]


@pytest.mark.parametrize(
    "content, message",
    [
        (None, "cannot read baseline"),
        ("not json", "is not a ramplint scan.json"),
        ('{"schema": 2}', "(schema 1)"),
        ('{"schema": 1, "violations": [{"code": "x"}]}', "no fingerprinted findings"),
    ],
)
def test_bad_baselines(tmp_path, content, message):
    path = tmp_path / "scan.json"
    if content is not None:
        path.write_text(content)
    with pytest.raises(BaselineError, match=message):
        load_baseline(path)


def test_baseline_end_to_end(site, tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    assert main([HOME, "--write-baseline", str(baseline)]) == EXIT_VIOLATIONS
    assert f"scan written to {baseline}" in capsys.readouterr().err

    # Nothing changed: only existing problems, the run passes.
    assert main([HOME, "--baseline", str(baseline)]) == EXIT_OK
    captured = capsys.readouterr()
    assert "RL101" not in captured.out
    assert "1 existing and 0 fixed problems are not shown" in captured.err
    assert "compared with" in captured.err and "0 new, 1 existing, 0 fixed" in captured.err

    # A new problem fails the run and is the only one shown.
    site.PAGES[f"{HOME}about/"] = lambda u, v: shot(u, v, BAD.replace('src="a.png"', 'src="b.png"'))
    assert main([HOME, "--baseline", str(baseline)]) == EXIT_VIOLATIONS
    out = capsys.readouterr().out
    assert out.count("RL101") == 1 and f"{HOME}about/" in out

    # JSON keeps every finding, with its status.
    main([HOME, "--baseline", str(baseline), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert sorted(v["baseline"] for v in data["violations"]) == ["existing", "new"]


def test_baseline_in_the_html_report(site, tmp_path):
    baseline = tmp_path / "baseline.json"
    main([HOME, "--write-baseline", str(baseline)])
    linked = GOOD.replace("<h1>Ok</h1>", '<h1>Ok</h1><a href="/about/">About</a>')
    site.PAGES[HOME] = lambda u, v: shot(u, v, linked)
    site.PAGES[f"{HOME}about/"] = lambda u, v: shot(u, v, BAD)
    folder = tmp_path / "a11y"
    main([HOME, "--baseline", str(baseline), "--format", "html", "-o", str(folder)])
    index = (folder / "index.html").read_text()
    assert "<dt>New</dt><dd>1</dd>" in index and "<dt>Fixed</dt><dd>1</dd>" in index
    assert 'id="filter-baseline"' in index and 'data-baseline="new"' in index
    assert "Fixed since the baseline (1)" in index
    assert lint_file(folder / "index.html") == []


def test_bad_baseline_file(site, tmp_path, capsys):
    assert main([HOME, "--baseline", str(tmp_path / "missing.json")]) == EXIT_ERROR
    assert "cannot read baseline" in capsys.readouterr().err
