"""Scanning behind a login: saved sessions, roles and their warnings."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ramplint.browser.auth import Role, roles, unprotected_secret
from ramplint.browser.command import combine
from ramplint.browser.frontier import Coverage
from ramplint.browser.scan import ScanResult
from ramplint.config import ConfigError, load_config
from ramplint.linter import Violation


def test_roles(tmp_path):
    admin = tmp_path / "admin.json"
    admin.write_text("{}")
    assert roles([str(admin)]) == [Role("admin", admin)]
    with pytest.raises(ValueError, match="does not exist"):
        roles([str(tmp_path / "missing.json")])
    other = tmp_path / "other"
    other.mkdir()
    (other / "admin.json").write_text("{}")
    with pytest.raises(ValueError, match="both called 'admin'"):
        roles([str(admin), str(other / "admin.json")])


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_unprotected_secret(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    assert not unprotected_secret(outside)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    auth = repo / "auth.json"
    auth.write_text("{}")
    assert unprotected_secret(auth)
    (repo / ".gitignore").write_text("auth.json\n")
    assert not unprotected_secret(auth)


def test_no_git(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    auth = tmp_path / "auth.json"
    auth.write_text("{}")
    assert not unprotected_secret(auth)


def test_auth_config(tmp_path):
    config = tmp_path / "pyproject.toml"
    config.write_text('[tool.ramplint.browser]\nauth = "auth/admin.json"\n')
    assert load_config(config).browser == {"auth": [str(tmp_path / "auth" / "admin.json")]}
    config.write_text('[tool.ramplint.browser]\nauth = ["a.json", "b.json"]\n')
    assert len(load_config(config).browser["auth"]) == 2
    config.write_text("[tool.ramplint.browser]\nauth = []\n")
    with pytest.raises(ConfigError, match="file name or a list"):
        load_config(config)


def finding(page: str, code: str = "RL101") -> Violation:
    return Violation(page, 1, 1, code, "img-alt", "m", url=page, selector="#x", viewport="desktop")


def test_findings_say_which_role_saw_them():
    admin = ScanResult(violations=[finding("http://x/"), finding("http://x/admin/", "RL501")])
    admin.coverage = [Coverage("/")]
    customer = ScanResult(violations=[finding("http://x/")])
    combined = combine(
        [(Role("admin", Path("a.json")), admin), (Role("customer", Path("c.json")), customer)]
    )
    assert [(v.path, v.code, v.role) for v in combined.violations] == [
        ("http://x/", "RL101", "admin,customer"),
        ("http://x/admin/", "RL501", "admin"),
    ]
    assert len(combined.coverage) == 1
    only = ScanResult()
    assert combine([(None, only)]) is only


def test_role_in_reports():
    import io
    import json

    from ramplint.reporters import REPORTERS, browser_report

    v = finding("http://x/")
    v = Violation(**{**v.__dict__, "role": "admin"})
    out = io.StringIO()
    with browser_report(["desktop"]):
        REPORTERS["text"].write([v], 1, out, False)
    assert "http://x/ #x [as admin]: RL101" in out.getvalue()
    out = io.StringIO()
    REPORTERS["sarif"].write([v], 1, out, False)
    assert json.loads(out.getvalue())["runs"][0]["results"][0]["properties"]["role"] == "admin"
