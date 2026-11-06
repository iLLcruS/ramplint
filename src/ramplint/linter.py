from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
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


#: Fields only set for problems found in a rendered page (browser mode).
BROWSER_FIELDS = ("url", "selector", "viewport", "bbox", "screenshot", "template", "pages")


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    col: int
    code: str
    name: str
    message: str
    # Browser mode only. Not part of equality or ordering, so template results
    # behave exactly as before. ``path`` is the URL and ``line``/``col`` point
    # into the rendered HTML.
    url: str | None = field(default=None, compare=False)
    #: Unique CSS selector of the element in the rendered page.
    selector: str | None = field(default=None, compare=False)
    #: Viewport(s) the problem was seen in, e.g. ``desktop`` or ``desktop,mobile``.
    viewport: str | None = field(default=None, compare=False)
    #: ``(x, y, width, height)`` of the element in CSS pixels.
    bbox: tuple[float, float, float, float] | None = field(default=None, compare=False)
    #: Picture of the element, relative to the report folder (set by the report).
    screenshot: str | None = field(default=None, compare=False)
    #: ``template.html:line`` that produced the element (set by the source map).
    template: str | None = field(default=None, compare=False)
    #: Every URL where the same problem was seen; ``path`` is the first of them.
    pages: tuple[str, ...] | None = field(default=None, compare=False)

    @property
    def in_browser(self) -> bool:
        return self.url is not None

    @property
    def locations(self) -> tuple[str, ...]:
        """The files or pages this problem is in."""
        return self.pages or (self.path,)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in BROWSER_FIELDS:
            if data[key] is None:
                del data[key]
        for key in ("bbox", "pages"):
            if key in data:
                data[key] = list(data[key])
        return data


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


def lint_python_source(
    source: str, path: str = "<string>", rules: Iterable[Rule] | None = None, index: Any = None
) -> list[Violation]:
    """Lint a Django forms module (``forms.py``)."""
    from ramplint.pyforms import lint_python_source as check

    active = list(rules) if rules is not None else select_rules()
    return sorted(
        {
            Violation(path=path, line=line, col=col, code=rule.code, name=rule.name, message=msg)
            for line, col, rule, msg in check(source, path, active, index)
        }
    )


def lint_file(
    path: str | Path, rules: Iterable[Rule] | None = None, context: Any = None, index: Any = None
) -> list[Violation]:
    path = Path(path)
    source = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return lint_python_source(source, path=path.as_posix(), rules=rules, index=index)
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
