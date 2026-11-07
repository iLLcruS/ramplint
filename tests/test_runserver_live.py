"""``ramplint --runserver`` on the demo project: Django + Chromium, end to end."""

from __future__ import annotations

from pathlib import Path

import pytest

from ramplint.cli import EXIT_VIOLATIONS, main

pytest.importorskip("django", reason="--runserver needs Django")
pytest.importorskip("jinja2", reason="the demo project has a Jinja2 backend")
pytestmark = [pytest.mark.browser, pytest.mark.usefixtures("chromium_available")]

DEMO = Path(__file__).resolve().parents[1] / "examples" / "django_project"


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.chdir(DEMO)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def test_findings_point_at_templates(demo, capsys):
    code = main(["--runserver", "--no-color", "--max-states", "0", "--select", "RL3,RL6"])
    assert code == EXIT_VIOLATIONS
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    # Seen by the template linter and again in the browser: reported once.
    heading = next(line for line in lines if " RL301 " in line)
    assert heading.startswith("catalog/templates/catalog/product_list.html:8:1: RL301")
    assert heading.endswith(", confirmed in the browser)")
    # Only the browser sees that base.html renders an empty <title> on this page.
    assert any(line.startswith("templates/base.html:7:3: RL603 <title> is empty") for line in lines)
    assert "starting config.settings.dev on http://127.0.0.1:" in captured.err
    assert "crawled 5 pages" in captured.err


def test_github_annotations_land_on_templates(demo, capsys):
    main(["--runserver", "--format", "github", "--max-states", "0", "--select", "RL301"])
    out = capsys.readouterr().out
    assert out.startswith(
        "::error file=catalog/templates/catalog/product_list.html,line=8,col=1,"
        "title=RL301 heading-order::"
    )


def log_in(page) -> None:
    """What a person does in the --save-auth window."""
    page.fill("#id_username", "ada")
    page.click("button[type=submit]")
    page.wait_for_url("**/accounts/profile/")
    page.close()


def test_pages_behind_login(demo, tmp_path, capsys):
    from ramplint.browser.auth import save_auth
    from ramplint.browser.options import BrowserOptions
    from ramplint.django.runserver import DevServer

    auth = tmp_path / "ada.json"
    with DevServer(DEMO, "config.settings.dev") as server:
        save_auth(f"{server.url}accounts/login/", auth, BrowserOptions(timeout=15), log_in)
    assert "sessionid" in auth.read_text()

    args = ["--runserver", "--no-color", "--max-states", "0", "--select", "RL4", "-v"]
    main(args)
    err = capsys.readouterr().err
    assert "/accounts/profile/   needs login" in err
    assert "redirected to the login page /accounts/login/" in err

    main([*args, "--auth", str(auth)])
    captured = capsys.readouterr()
    assert "ramplint: scanning as ada" in captured.err
    assert "/accounts/profile/   scanned (1 of 1)" in captured.err
    # The profile form is only visible logged in: its unlabelled fields are found.
    assert "RL401" in captured.out and "[as ada]" in captured.out
