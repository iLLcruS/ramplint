from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ramplint import dom
from ramplint.rules import Rule, select_rules
from ramplint.template import prepare

DEFAULT_EXTENSIONS = (".html", ".htm", ".jinja", ".jinja2", ".j2", ".djhtml")
# fmt: off
DEFAULT_EXCLUDE_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", ".tox", ".nox", ".venv", "venv", "env",
        "node_modules", "__pycache__", "build", "dist", "site-packages",
        ".mypy_cache", ".pytest_cache", ".ruff_cache", "htmlcov",
    }
)
# fmt: on


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    col: int
    code: str
    name: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def lint_source(
    source: str,
    path: str = "<string>",
    rules: Iterable[Rule] | None = None,
    context: Any = None,
) -> list[Violation]:
    """Lint template source code and return the problems found.

    ``context`` (a :class:`ramplint.project.context.TemplateContext`) lets
    rules look at the templates this one extends and includes.
    """
    active = list(rules) if rules is not None else select_rules()
    prepared = prepare(source)
    root = dom.parse(prepared.html, branch_of=prepared.branches.at, source=source)
    if context is not None and context.template.source == source:
        root.context = context
        context.template.__dict__["root"] = root  # reuse this parse
    violations: set[Violation] = set()
    for rule in active:
        for node, message in rule.check(root):
            if prepared.suppressions.is_suppressed(node.line, rule.code, rule.name):
                continue
            violations.add(
                Violation(
                    path=path,
                    line=node.line,
                    col=node.col,
                    code=rule.code,
                    name=rule.name,
                    message=message,
                )
            )
    return sorted(violations)


def lint_file(
    path: str | Path, rules: Iterable[Rule] | None = None, context: Any = None
) -> list[Violation]:
    path = Path(path)
    source = path.read_text(encoding="utf-8", errors="replace")
    return lint_source(source, path=path.as_posix(), rules=rules, context=context)


def _is_excluded(path: Path, patterns: Iterable[str]) -> bool:
    posix = path.as_posix()
    return any(
        fnmatch.fnmatch(posix, pattern) or fnmatch.fnmatch(path.name, pattern)
        for pattern in patterns
    )


def iter_template_files(
    paths: Iterable[str | Path],
    extensions: Iterable[str] = DEFAULT_EXTENSIONS,
    exclude: Iterable[str] = (),
) -> Iterator[Path]:
    """Yield template files under ``paths``.

    Files passed explicitly are always yielded (so pre-commit can hand us any
    file it likes); directories are walked recursively.
    """
    extensions = tuple(e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions)
    exclude = list(exclude)
    seen: set[Path] = set()
    for raw in paths:
        root = Path(raw)
        if root.is_file():
            if root not in seen and not _is_excluded(root, exclude):
                seen.add(root)
                yield root
            continue
        if not root.is_dir():
            raise FileNotFoundError(raw)
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            dirnames[:] = sorted(
                d
                for d in dirnames
                if d not in DEFAULT_EXCLUDE_DIRS
                and not d.endswith(".egg-info")
                and not _is_excluded(current / d, exclude)
            )
            for filename in sorted(filenames):
                file_path = current / filename
                if not filename.lower().endswith(extensions):
                    continue
                if file_path in seen or _is_excluded(file_path, exclude):
                    continue
                seen.add(file_path)
                yield file_path
