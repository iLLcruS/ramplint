"""``--changed [REF]``: lint only the files git says changed."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ramplint.changed import ChangedFilesError, changed_files
from ramplint.cli import EXIT_ERROR, EXIT_OK, EXIT_VIOLATIONS, main

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

BAD = '<img src="a.png">\n'


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "old.html").write_text(BAD)
    (tmp_path / "templates" / "edited.html").write_text("<p>ok</p>\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "start")
    return tmp_path


def test_uncommitted_and_untracked_files(repo, capsys):
    (repo / "templates" / "edited.html").write_text(BAD)
    (repo / "templates" / "new.html").write_text(BAD)
    assert main(["--no-color", "--changed"]) == EXIT_VIOLATIONS
    out = capsys.readouterr().out
    assert "templates/edited.html" in out
    assert "templates/new.html" in out
    assert "old.html" not in out
    assert "(2 files)" in out or "of 2 files" in out


def test_nothing_changed(repo, capsys):
    assert main(["--changed"]) == EXIT_OK
    assert "(0 files)" in capsys.readouterr().out


def test_branch_compared_with_where_it_started(repo, capsys):
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "templates" / "edited.html").write_text(BAD)
    git(repo, "commit", "-q", "-am", "feature work")
    git(repo, "checkout", "-q", "main")
    (repo / "templates" / "main_only.html").write_text(BAD)
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "main moves on")
    git(repo, "checkout", "-q", "feature")
    assert main(["--no-color", "--changed", "main"]) == EXIT_VIOLATIONS
    out = capsys.readouterr().out
    assert "templates/edited.html" in out
    assert "main_only.html" not in out


def test_deleted_files_are_skipped(repo):
    (repo / "templates" / "old.html").unlink()
    assert changed_files("HEAD", repo) == set()


def test_unknown_ref(repo, capsys):
    assert main(["--changed", "no-such-branch"]) == EXIT_ERROR
    assert "ramplint: error: --changed:" in capsys.readouterr().err


def test_not_a_repository(tmp_path):
    with pytest.raises(ChangedFilesError):
        changed_files("HEAD", tmp_path)


def test_git_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ChangedFilesError, match="git is not installed"):
        changed_files("HEAD", tmp_path)


def test_baseline_only_counts_checked_files(repo, capsys):
    main(["--write-baseline", "baseline.json"])
    (repo / "templates" / "edited.html").write_text("<p>still ok</p>\n")
    capsys.readouterr()
    assert main(["--changed", "--baseline", "baseline.json"]) == EXIT_OK
    assert "0 new, 0 existing, 0 fixed" in capsys.readouterr().err


def test_write_baseline_needs_every_file(repo, capsys):
    assert main(["--changed", "--write-baseline", "b.json"]) == EXIT_ERROR
    assert "do not use it with --changed" in capsys.readouterr().err


def test_urls_are_rejected(repo, capsys):
    assert main(["http://localhost:8000/", "--changed"]) == EXIT_ERROR
    assert "--changed works with templates" in capsys.readouterr().err


def test_verbose(repo, capsys):
    main(["--changed", "-v"])
    assert "0 changed files since HEAD" in capsys.readouterr().err
