from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ramplint.dom import Node

#: A check yields ``(node, message)`` pairs for every problem it finds.
Check = Callable[[Node], Iterator[tuple[Node, str]]]


#: A check of a Python module (``forms.py``): yields ``(line, col, message)``.
PythonCheck = Callable[[Any], Iterator[tuple[int, int, str]]]


def _no_template_check(root: Node) -> Iterator[tuple[Node, str]]:
    return iter(())


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    summary: str
    wcag: str
    check: Check
    #: Set for rules that check Python code (Django forms) instead of templates.
    python_check: PythonCheck | None = None

    @property
    def docs_url(self) -> str:
        """The rule's documentation page on GitHub."""
        return f"{DOCS_BASE_URL}/{self.code}.md"


DOCS_BASE_URL = "https://github.com/iLLcruS/ramplint/blob/main/docs/rules"

REGISTRY: dict[str, Rule] = {}


def rule(code: str, name: str, summary: str, wcag: str) -> Callable[[Check], Check]:
    """Register a check function as a rule."""

    def decorator(func: Check) -> Check:
        if code in REGISTRY:  # pragma: no cover - programming error
            raise ValueError(f"Duplicate rule code {code}")
        REGISTRY[code] = Rule(code=code, name=name, summary=summary, wcag=wcag, check=func)
        return func

    return decorator


def python_rule(
    code: str, name: str, summary: str, wcag: str
) -> Callable[[PythonCheck], PythonCheck]:
    """Register a check of Python modules (see :mod:`ramplint.pyforms`)."""

    def decorator(func: PythonCheck) -> PythonCheck:
        if code in REGISTRY:  # pragma: no cover - programming error
            raise ValueError(f"Duplicate rule code {code}")
        REGISTRY[code] = Rule(
            code=code,
            name=name,
            summary=summary,
            wcag=wcag,
            check=_no_template_check,
            python_check=func,
        )
        return func

    return decorator
