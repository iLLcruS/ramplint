"""Lint Django form modules (``forms.py``) with ``ast``, without importing them."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SUPPRESS_RE = re.compile(r"#\s*ramplint:\s*(ignore-file|ignore)\b([^\n]*)")
_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
_GETTEXT = frozenset({"_", "gettext", "gettext_lazy", "ugettext", "ugettext_lazy", "pgettext"})


def is_forms_module(path: Path) -> bool:
    """``forms.py`` or a module of a ``forms`` package."""
    return path.suffix == ".py" and (path.name == "forms.py" or path.parent.name == "forms")


@dataclass
class PythonModule:
    path: Path
    source: str
    tree: ast.Module
    #: Template names -> files (a :class:`ramplint.project.templates.TemplateIndex`).
    index: Any = None

    def classes(self) -> Iterator[ast.ClassDef]:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                yield node


def name_of(node: ast.AST) -> str:
    """``forms.CharField`` -> ``CharField``; ``_("x")`` -> ``_``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return name_of(node.func)
    return ""


def keyword(call: ast.Call, name: str) -> ast.keyword | None:
    return next((k for k in call.keywords if k.arg == name), None)


def string_value(node: ast.AST | None) -> str | None:
    """A literal string, also inside ``_("...")`` / ``gettext_lazy("...")``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if (
        isinstance(node, ast.Call)
        and len(node.args) == 1
        and not node.keywords
        and name_of(node.func) in _GETTEXT
    ):
        return string_value(node.args[0])
    return None


def dict_keys(node: ast.AST | None) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _suppressions(source: str) -> tuple[set[str] | None, dict[int, set[str]]]:
    whole: set[str] | None = None
    by_line: dict[int, set[str]] = {}
    for match in _SUPPRESS_RE.finditer(source):
        codes = set(_CODE_RE.findall(match.group(2)))
        if match.group(1) == "ignore-file":
            whole = set() if not codes else (whole or set()) | codes
            continue
        line = source.count("\n", 0, match.start()) + 1
        for target in (line, line + 1):
            by_line.setdefault(target, set()).update(codes or {"*"})
    return whole, by_line


def _suppressed(whole: set[str] | None, by_line: dict[int, set[str]], line: int, rule: Any) -> bool:
    if whole is not None and (not whole or rule.code in whole or rule.name in whole):
        return True
    codes = by_line.get(line)
    return bool(codes) and ("*" in codes or rule.code in codes or rule.name in codes)


def lint_python_source(
    source: str, path: str, rules: Iterable[Any], index: Any = None
) -> list[tuple[int, int, Any, str]]:
    """``(line, col, rule, message)`` for every problem in a Python module."""
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError):
        return []
    module = PythonModule(path=Path(path), source=source, tree=tree, index=index)
    whole, by_line = _suppressions(source)
    found = []
    for rule in rules:
        if rule.python_check is None:
            continue
        for line, col, message in rule.python_check(module):
            if not _suppressed(whole, by_line, line, rule):
                found.append((line, col, rule, message))
    return found
