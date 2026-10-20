from __future__ import annotations

import textwrap

import pytest

from ramplint import lint_source, select_rules


@pytest.fixture
def lint():
    """Lint a template snippet, optionally restricted to some rules.

    Returns a list of ``(code, line)`` tuples for compact assertions.
    """

    def _lint(source: str, *select: str) -> list[tuple[str, int]]:
        rules = select_rules(list(select)) if select else None
        violations = lint_source(textwrap.dedent(source), rules=rules)
        return [(v.code, v.line) for v in violations]

    return _lint
