"""``--fix``: safe, unambiguous rewrites of attribute values."""

from __future__ import annotations

from pathlib import Path

import pytest

from ramplint import select_rules
from ramplint.cli import EXIT_ERROR, EXIT_OK, EXIT_VIOLATIONS, main
from ramplint.fix import apply_fixes, find_fixes, fix_source


def fixed(source: str) -> str:
    return fix_source(source, select_rules())[0]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ('<th scope="column">A</th>', '<th scope="col">A</th>'),
        ("<th scope='rows'>A</th>", "<th scope='row'>A</th>"),
        ("<th scope=Column>A</th>", '<th scope="col">A</th>'),
        ('<input autocomplete="emial">', '<input autocomplete="email">'),
        ('<input autocomplete="shipping zip">', '<input autocomplete="shipping postal-code">'),
        ('<input autocomplete="firstname">', '<input autocomplete="given-name">'),
        ('<a href="/" tabindex="3">x</a>', '<a href="/" tabindex="0">x</a>'),
        ('<div tabindex=+2 role="button">x</div>', '<div tabindex="0" role="button">x</div>'),
        (
            '<meta name="viewport" content="width=device-width, maximum-scale=1.0, '
            'user-scalable=no">',
            '<meta name="viewport" content="width=device-width">',
        ),
        (
            '<meta name="viewport" content="width=device-width;user-scalable=0">',
            '<meta name="viewport" content="width=device-width">',
        ),
        (
            '<meta name="viewport" content="maximum-scale=big, user-scalable=no">',
            '<meta name="viewport" content="maximum-scale=big">',
        ),
        ('<html lang="ua">', '<html lang="uk">'),
        ('<p lang="en_US">x</p>', '<p lang="en-US">x</p>'),
        ('<html lang="english" xml:lang="english">', '<html lang="en" xml:lang="en">'),
    ],
)
def test_fixes(before, after):
    assert fixed(before) == after


@pytest.mark.parametrize(
    "source",
    [
        '<td scope="col">x</td>',  # needs a <th>, not a new value
        '<th scope="xyzzy">A</th>',  # no confident suggestion
        '<input autocomplete="password">',  # current-password or new-password?
        '<input autocomplete="qqqq">',
        '<form autocomplete="nope"></form>',
        '<input autocomplete="{{ kind }}">',
        '<input {{ attrs }} autocomplete="emial">',
        '<div tabindex="{{ order }}">x</div>',
        '<html lang="zz-top-secret-value">',
        '<html lang="en" xml:lang="ro">',  # different languages: a person decides
        '<meta name="viewport" content="width=device-width, maximum-scale=5">',
        '<input autocomplete="emial"> {# ramplint: ignore RL402 #}',
        "<!-- ramplint: ignore-file -->\n<html lang=ua>",
    ],
)
def test_left_alone(source):
    assert fixed(source) == source


def test_template_tags_around_the_tag_keep_their_place():
    source = (
        '{% load i18n %}\n<table>{% for r in rows %}<tr><th scope="column" '
        'class="{% if r.x %}x{% endif %}">{{ r }}</th></tr>{% endfor %}</table>\n'
    )
    assert fixed(source) == source.replace('scope="column"', 'scope="col"')


def test_rules_that_are_not_selected_are_not_fixed():
    source = '<html lang="ua"><a href="/" tabindex="2">x</a></html>'
    new, fixes = fix_source(source, select_rules(["RL503"]))
    assert new == '<html lang="ua"><a href="/" tabindex="0">x</a></html>'
    assert [f.code for f in fixes] == ["RL503"]


def test_overlapping_fixes_are_skipped():
    fixes = find_fixes('<th scope="column">A</th>', select_rules())
    assert apply_fixes('<th scope="column">A</th>', fixes * 2) == '<th scope="col">A</th>'


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    (tmp_path / "templates").mkdir()
    return tmp_path


def test_cli_fixes_files_and_reports_the_rest(project, capsys):
    page = project / "templates" / "page.html"
    page.write_bytes(b'<html lang="ua">\r\n<img src="a.png">\r\n<th scope="column">A</th>\r\n')
    assert main(["--no-color", "--fix"]) == EXIT_VIOLATIONS
    captured = capsys.readouterr()
    assert "ramplint: fixed 2 problems in 1 file" in captured.err
    assert "RL101" in captured.out
    assert "RL604" not in captured.out
    # Line endings are kept.
    assert (
        page.read_bytes() == b'<html lang="uk">\r\n<img src="a.png">\r\n<th scope="col">A</th>\r\n'
    )


def test_cli_fix_everything(project, capsys):
    (project / "templates" / "a.html").write_text('<a href="/" tabindex="1">A</a>\n')
    (project / "templates" / "b.html").write_text('<a href="/" tabindex="2">B</a>\n')
    assert main(["--fix"]) == EXIT_OK
    assert "fixed 2 problems in 2 files" in capsys.readouterr().err


def test_cli_nothing_to_fix_is_quiet(project, capsys):
    (project / "templates" / "a.html").write_text("<p>ok</p>\n")
    assert main(["--fix"]) == EXIT_OK
    assert "fixed" not in capsys.readouterr().err


def test_cli_fix_skips_forms_and_unreadable_files(project, capsys):
    (project / "templates" / "bad.html").write_bytes(b"\xff\xfe<html lang=ua>")
    (project / "forms.py").write_text("x = 1\n")
    main(["--fix", "templates/bad.html", "forms.py"])
    assert "fixed" not in capsys.readouterr().err


def test_cli_fix_cannot_write(project, capsys, monkeypatch):
    page = project / "templates" / "a.html"
    page.write_text('<html lang="ua"></html>\n')
    real_open = open

    def fake_open(path, mode="r", *args, **kwargs):
        if "w" in mode:
            raise PermissionError("read-only")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    assert main(["--fix"]) == EXIT_ERROR
    assert f"cannot write {Path('templates') / 'a.html'}" in capsys.readouterr().err


def test_cli_fix_does_not_work_with_urls(project, capsys):
    assert main(["--fix", "http://localhost:8000/"]) == EXIT_ERROR
    assert "--fix works with templates" in capsys.readouterr().err
