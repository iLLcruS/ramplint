"""Keep the README honest: its examples must match what ramplint really does."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ramplint import lint_source
from ramplint.cli import main

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")

# Lines like:  {# ✗ #} <img src="logo.png">
EXAMPLE_RE = re.compile(r"^\{# (✗|✓) #\} (.*)$", re.MULTILINE)
EXAMPLES = EXAMPLE_RE.findall(README)


def test_readme_has_examples():
    assert len(EXAMPLES) > 20


@pytest.mark.parametrize(("mark", "snippet"), EXAMPLES, ids=[s[:60] for _, s in EXAMPLES])
def test_readme_rule_examples(mark, snippet):
    problems = lint_source(snippet)
    if mark == "✗":
        assert problems, "README marks this snippet as bad, but ramplint reports nothing"
    else:
        assert not problems, f"README marks this snippet as good, but got {problems}"


def test_readme_sample_output_matches_real_output(capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    main(["examples", "--no-color"])
    real_output = capsys.readouterr().out.splitlines()

    sample = [
        line
        for line in README.splitlines()
        if line.startswith("examples/templates/") or line.startswith("Found ")
    ]
    assert sample, "README sample output not found"
    for line in sample:
        assert line in real_output, f"README sample line is out of date:\n{line}"


def test_changelog_has_section_for_current_version():
    from ramplint import __version__

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}] - " in changelog, "add a CHANGELOG section before releasing"
    assert f"[{__version__}]: https://github.com/" in changelog


def test_readme_pre_commit_rev_matches_version():
    from ramplint import __version__

    assert f"rev: {__version__}\n" in README


def test_readme_links_are_absolute():
    """PyPI renders the README without the repository files, so relative
    links and images break there."""
    prose = re.sub(r"```.*?```", "", README, flags=re.DOTALL)
    targets = re.findall(r"\]\(([^)\s]+)\)|(?:src|href)=\"([^\"]+)\"", prose)
    relative = [
        url for pair in targets for url in pair if url and not re.match(r"(https?:|mailto:|#)", url)
    ]
    assert not relative, f"use absolute GitHub URLs in README: {relative}"


def test_readme_statistics_sample_matches_real_output(capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    main(["examples", "--statistics", "--no-color"])
    real_output = capsys.readouterr().out
    sample = README.split("$ ramplint examples/ --statistics\n", 1)[1].split("```", 1)[0]
    assert sample == real_output


def test_readme_list_templates_sample_matches_real_output(capsys, monkeypatch):
    monkeypatch.chdir(ROOT / "examples" / "django_project")
    main(["--list-templates"])
    real_output = capsys.readouterr().out
    sample = README.split("$ cd examples/django_project && ramplint --list-templates\n", 1)[1]
    assert sample.split("```", 1)[0] == real_output


def test_license_files_match_metadata():
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expression = pyproject["project"]["license"]
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("Required Notice: Copyright Vladyslav Rostovskyi")
    for spdx in expression.split(" OR "):
        page = ROOT / "LICENSES" / f"{spdx}.md"
        assert page.is_file(), page
        assert f"LICENSES/{spdx}.md" in license_text
    assert (ROOT / "COMMERCIAL.md").is_file()
