from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ramplint import __version__, all_rules
from ramplint.cli import EXIT_ERROR, EXIT_OK, EXIT_VIOLATIONS, main

BAD = '<img src="a.png">\n<a href="/"></a>\n'
GOOD = '<img src="a.png" alt="Logo">\n'


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    (tmp_path / "templates" / "shop").mkdir(parents=True)
    (tmp_path / "templates" / "shop" / "bad.html").write_text(BAD)
    (tmp_path / "templates" / "good.html").write_text(GOOD)
    (tmp_path / "templates" / "notes.txt").write_text(BAD)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "vendor.html").write_text(BAD)
    return tmp_path


def test_reports_problems(project, capsys):
    assert main(["--no-color"]) == EXIT_VIOLATIONS
    out = capsys.readouterr().out
    assert "templates/shop/bad.html:1:1: RL101" in out
    assert "templates/shop/bad.html:2:1: RL502" in out
    assert "node_modules" not in out
    assert "notes.txt" not in out
    assert "Found 2 problems in 1 of 2 files." in out


def test_clean_run(project, capsys):
    assert main(["templates/good.html"]) == EXIT_OK
    assert "All checks passed (1 file)." in capsys.readouterr().out


def test_explicit_file_with_any_extension(project, capsys):
    assert main(["templates/notes.txt"]) == EXIT_VIOLATIONS


def test_select_and_ignore(project, capsys):
    assert main(["--select", "RL1"]) == EXIT_VIOLATIONS
    assert "RL502" not in capsys.readouterr().out
    assert main(["--ignore", "img-alt,link-name"]) == EXIT_OK


def test_unknown_rule(project, capsys):
    assert main(["--select", "RL999"]) == EXIT_ERROR
    assert "unknown rule" in capsys.readouterr().err


def test_exclude(project, capsys):
    assert main(["--exclude", "templates/shop/*"]) == EXIT_OK


def test_exit_zero(project):
    assert main(["--exit-zero"]) == EXIT_OK


def test_missing_path(project, capsys):
    assert main(["nope"]) == EXIT_ERROR


def test_json_format(project, capsys):
    main(["--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data["files_checked"] == 2
    assert [v["code"] for v in data["violations"]] == ["RL101", "RL502"]


def test_github_format(project, capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    main([])
    out = capsys.readouterr().out
    assert "::error file=templates/shop/bad.html,line=1,col=1,title=RL101 img-alt::" in out


def test_pyproject_config(project, capsys):
    (project / "pyproject.toml").write_text(
        '[tool.ramplint]\nignore = ["RL502"]\nexclude = ["*/good.html"]\n'
    )
    assert main(["--format", "json"]) == EXIT_VIOLATIONS
    data = json.loads(capsys.readouterr().out)
    assert data["files_checked"] == 1
    assert [v["code"] for v in data["violations"]] == ["RL101"]


def test_bad_config(project, capsys):
    (project / "pyproject.toml").write_text("[tool.ramplint]\nselct = []\n")
    assert main([]) == EXIT_ERROR
    assert "unknown option" in capsys.readouterr().err


def test_list_rules(capsys):
    assert main(["--list-rules"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "RL101  img-alt" in out
    assert out.count("\n") == len(all_rules())


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out


def test_examples_directory(capsys, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    main(["examples", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    by_file: dict[str, list[str]] = {}
    for v in data["violations"]:
        by_file.setdefault(Path(v["path"]).name, []).append(v["code"])
    assert data["files_checked"] == 8
    assert len(data["violations"]) == 32
    # Clean templates must stay silent - they guard against false positives.
    assert "list_fixed.html" not in by_file
    assert "tricky_but_valid.html" not in by_file
    assert sorted(by_file["list.html"]) == ["RL101", "RL201", "RL301", "RL401", "RL501", "RL502"]
    # The demo covers every rule.
    all_codes = {code for codes in by_file.values() for code in codes}
    assert all_codes == {rule.code for rule in all_rules()}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX pipe semantics")
def test_closed_pipe_does_not_print_traceback(tmp_path):
    import subprocess

    template = tmp_path / "many.html"
    template.write_text('<img src="a.png">\n' * 5000)
    proc = subprocess.Popen(
        [sys.executable, "-m", "ramplint", str(template), "--no-color"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    proc.stdout.readline()
    proc.stdout.close()  # like `| head -1`
    stderr = proc.stderr.read().decode()
    proc.wait(timeout=30)
    assert "Traceback" not in stderr
    assert "BrokenPipeError" not in stderr
