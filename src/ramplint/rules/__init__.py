"""Built-in rules.

Importing this package registers every rule in :data:`REGISTRY`.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from ramplint.rules import (  # noqa: F401
    controls,
    document,
    embeds,
    forms,
    headings,
    ids,
    images,
    tables,
)
from ramplint.rules.base import REGISTRY, Rule


def all_rules() -> list[Rule]:
    return sorted(REGISTRY.values(), key=lambda r: r.code)


def _matches(rule: Rule, selector: str) -> bool:
    selector = selector.strip()
    if not selector:
        return False
    return rule.code.startswith(selector.upper()) or rule.name == selector.lower()


def select_rules(select: list[str] | None = None, ignore: list[str] | None = None) -> list[Rule]:
    """Pick rules by code prefix (``RL1``, ``RL101``) or name (``img-alt``)."""
    rules = all_rules()
    if select:
        rules = [r for r in rules if any(_matches(r, s) for s in select)]
    if ignore:
        rules = [r for r in rules if not any(_matches(r, s) for s in ignore)]
    return rules


def find_rule(selector: str) -> Rule | None:
    """Exact lookup by code (``RL101``) or name (``img-alt``)."""
    selector = selector.strip()
    for rule in all_rules():
        if rule.code == selector.upper() or rule.name == selector.lower():
            return rule
    return None


def rule_docs(rule: Rule) -> str | None:
    """The rule's Markdown documentation, or None if it is not available.

    Installed packages ship the pages as ``ramplint/rule_docs``; a source
    checkout reads them from ``docs/rules``.
    """
    filename = f"{rule.code}.md"
    packaged = files("ramplint").joinpath("rule_docs", filename)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    checkout = Path(__file__).resolve().parents[3] / "docs" / "rules" / filename
    if checkout.is_file():
        return checkout.read_text(encoding="utf-8")
    return None


def unknown_selectors(selectors: list[str]) -> list[str]:
    rules = all_rules()
    return [s for s in selectors if s.strip() and not any(_matches(r, s) for r in rules)]


__all__ = [
    "REGISTRY",
    "Rule",
    "all_rules",
    "find_rule",
    "rule_docs",
    "select_rules",
    "unknown_selectors",
]
