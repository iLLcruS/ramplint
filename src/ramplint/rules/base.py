from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from ramplint.dom import Node

#: A check yields ``(node, message)`` pairs for every problem it finds.
Check = Callable[[Node], Iterator[tuple[Node, str]]]


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    summary: str
    wcag: str
    check: Check

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
