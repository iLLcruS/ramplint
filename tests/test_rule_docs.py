"""Every rule has a documentation page, and the page's examples are true."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ramplint import lint_source
from ramplint.cli import EXIT_ERROR, EXIT_OK, main
from ramplint.linter import lint_python_source
from ramplint.rules import all_rules, rule_docs

DOCS = Path(__file__).resolve().parents[1] / "docs" / "rules"
RULES = all_rules()
IDS = [rule.code for rule in RULES]


def _block(page: str, heading: str, language: str = "django") -> list[str]:
    """Code lines of the ```django (or ```python) block right after ``heading``."""
    after = page.split(f"{heading}\n", 1)[1]
    code = re.search(rf"```{language}\n(.*?)```", after, re.DOTALL).group(1)
    return [re.sub(r"^\{# [✗✓] #\} ", "", line) for line in code.splitlines()]


def _codes(source: str) -> set[str]:
    return {v.code for v in lint_source(source)}


def _python_codes(source: str) -> set[str]:
    return {v.code for v in lint_python_source(source, "forms.py")}


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_page_exists_and_matches_rule(rule):
    page = (DOCS / f"{rule.code}.md").read_text(encoding="utf-8")
    assert page.startswith(f"# {rule.code} `{rule.name}`\n\n{rule.summary}\n")
    for section in ("## WCAG", "## Why it matters", "## What ramplint reports", "## Examples"):
        assert section in page, f"{rule.code}.md is missing {section}"
    assert f"ramplint: ignore {rule.code}" in page


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_problem_examples_are_reported(rule):
    page = (DOCS / f"{rule.code}.md").read_text(encoding="utf-8")
    if rule.python_check is not None:
        assert rule.code in _python_codes("\n".join(_block(page, "Problems:", "python")))
        return
    problems = "\n".join(_block(page, "Problems:"))
    assert rule.code in _codes(problems)


@pytest.mark.parametrize("rule", RULES, ids=IDS)
def test_fixed_examples_are_not_reported(rule):
    page = (DOCS / f"{rule.code}.md").read_text(encoding="utf-8")
    if rule.python_check is not None:
        assert rule.code not in _python_codes("\n".join(_block(page, "Fixed:", "python")))
        return
    fixed = _block(page, "Fixed:")
    for line in fixed:
        assert rule.code not in _codes(line), line
    assert rule.code not in _codes("\n".join(fixed))


def test_no_pages_for_unknown_rules():
    pages = {p.stem for p in DOCS.glob("RL*.md")}
    assert pages == set(IDS)


def test_index_lists_every_rule():
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    for rule in RULES:
        assert f"[{rule.code}]({rule.code}.md)" in index


def test_rule_docs_loader():
    assert rule_docs(RULES[0]).startswith(f"# {RULES[0].code}")


def test_explain_by_code_and_name(capsys):
    assert main(["--explain", "RL303"]) == EXIT_OK
    out = capsys.readouterr().out
    assert out.startswith("# RL303 `duplicate-id`")
    assert "Online: https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL303.md" in out
    assert main(["--explain", "img-alt"]) == EXIT_OK
    assert capsys.readouterr().out.startswith("# RL101 `img-alt`")


def test_explain_unknown_rule(capsys):
    assert main(["--explain", "RL999"]) == EXIT_ERROR
    assert "unknown rule: RL999" in capsys.readouterr().err


def test_list_rules_is_aligned(capsys):
    main(["--list-rules"])
    lines = capsys.readouterr().out.splitlines()
    summary_columns = {line.index(rule.summary) for line, rule in zip(lines, RULES, strict=True)}
    assert len(summary_columns) == 1
