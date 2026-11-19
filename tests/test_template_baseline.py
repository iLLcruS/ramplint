"""``--baseline`` / ``--write-baseline`` without URLs: the template linter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ramplint.cli import EXIT_ERROR, EXIT_OK, EXIT_VIOLATIONS, main

BAD = '<img src="a.png">\n<a href="/"></a>\n'


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "page.html").write_text(BAD)
    return tmp_path


def test_write_baseline_succeeds_and_stores_fingerprints(project, capsys):
    assert main(["--no-color", "--write-baseline", "a11y/baseline.json"]) == EXIT_OK
    captured = capsys.readouterr()
    target = Path("a11y") / "baseline.json"
    assert f"baseline with 2 problems written to {target}" in captured.err
    assert "RL101" in captured.out  # the report is still printed
    data = json.loads((project / "a11y" / "baseline.json").read_text())
    assert data["schema"] == 1
    assert data["mode"] == "templates"
    assert data["files_checked"] == 1
    assert {v["code"] for v in data["violations"]} == {"RL101", "RL502"}
    assert all(len(v["fingerprint"]) == 16 for v in data["violations"])
    assert all("baseline" not in v for v in data["violations"])


def test_baseline_hides_existing_problems(project, capsys):
    main(["--write-baseline", "baseline.json"])
    capsys.readouterr()
    assert main(["--no-color", "--baseline", "baseline.json"]) == EXIT_OK
    captured = capsys.readouterr()
    assert "RL101" not in captured.out
    assert "0 new, 2 existing, 0 fixed" in captured.err
    assert "2 existing and 0 fixed problems are not shown" in captured.err


def test_new_problem_fails_and_line_moves_do_not(project, capsys):
    main(["--write-baseline", "baseline.json"])
    page = project / "templates" / "page.html"
    page.write_text("\n\n" + BAD + "<button></button>\n")
    capsys.readouterr()
    assert main(["--no-color", "--baseline", "baseline.json"]) == EXIT_VIOLATIONS
    captured = capsys.readouterr()
    assert "RL501" in captured.out
    assert "RL101" not in captured.out
    assert "1 new, 2 existing, 0 fixed" in captured.err


def test_fixed_problems_are_counted(project, capsys):
    main(["--write-baseline", "baseline.json"])
    (project / "templates" / "page.html").write_text('<a href="/"></a>\n')
    capsys.readouterr()
    assert main(["--baseline", "baseline.json"]) == EXIT_OK
    assert "0 new, 1 existing, 1 fixed" in capsys.readouterr().err


def test_json_report_keeps_every_problem_with_its_state(project, capsys):
    main(["--write-baseline", "baseline.json"])
    (project / "templates" / "page.html").write_text(BAD + "<button></button>\n")
    capsys.readouterr()
    assert main(["--format", "json", "--baseline", "baseline.json"]) == EXIT_VIOLATIONS
    data = json.loads(capsys.readouterr().out)
    states = sorted((v["code"], v["baseline"]) for v in data["violations"])
    assert states == [("RL101", "existing"), ("RL501", "new"), ("RL502", "existing")]


def test_sarif_has_baseline_state(project, capsys):
    main(["--write-baseline", "baseline.json"])
    capsys.readouterr()
    main(["--format", "sarif", "--baseline", "baseline.json"])
    results = json.loads(capsys.readouterr().out)["runs"][0]["results"]
    assert {r["baselineState"] for r in results} == {"unchanged"}


def test_html_report_lists_fixed_problems(project, capsys):
    main(["--write-baseline", "baseline.json"])
    (project / "templates" / "page.html").write_text('<a href="/"></a>\n')
    capsys.readouterr()
    main(["--format", "html", "-o", "report.html", "--baseline", "baseline.json"])
    html = (project / "report.html").read_text()
    assert "Fixed since the baseline (1)" in html


def test_exit_zero_with_new_problems(project, capsys):
    main(["--write-baseline", "baseline.json"])
    (project / "templates" / "page.html").write_text("<button></button>\n")
    assert main(["--baseline", "baseline.json", "--exit-zero"]) == EXIT_OK


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "cannot read baseline"),
        ("not json", "is not a ramplint scan.json"),
        ('{"schema": 2}', "(schema 1)"),
    ],
)
def test_unusable_baseline(project, capsys, content, message):
    if content is not None:
        (project / "baseline.json").write_text(content)
    assert main(["--baseline", "baseline.json"]) == EXIT_ERROR
    assert message in capsys.readouterr().err


def test_baseline_cannot_be_written(project, capsys):
    (project / "taken").write_text("")
    assert main(["--write-baseline", "taken/baseline.json"]) == EXIT_ERROR
    assert "cannot write baseline" in capsys.readouterr().err


def test_baseline_does_not_need_urls(project, capsys):
    (project / "pyproject.toml").write_text(
        '[tool.ramplint.browser]\nbase-url = "http://localhost:8000/"\n'
    )
    main(["--write-baseline", "baseline.json"])
    assert "needs URLs" not in capsys.readouterr().err
    assert (project / "baseline.json").exists()


def test_report_cannot_be_written_with_baseline(project, capsys):
    main(["--write-baseline", "baseline.json"])
    (project / "taken").write_text("")
    assert main(["--baseline", "baseline.json", "-o", "taken/report.txt"]) == EXIT_ERROR
    assert "cannot write report" in capsys.readouterr().err
