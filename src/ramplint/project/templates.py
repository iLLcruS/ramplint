"""Template names, ``{% extends %}`` / ``{% include %}`` references and blocks."""

from __future__ import annotations

import os
import re
from bisect import bisect_right
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from ramplint import dom
from ramplint.template import Token, prepare, strip_comments, tokens

#: ``{% extends "base.html" %}``, ``{% include 'a.html' with x=1 %}``,
#: ``{% import "macros.html" as m %}``, ``{% from "forms.html" import field %}``.
_REFERENCE_RE = re.compile(r"""\{%-?\s*(extends|include|import|from)\s+(["'])([^"']+)\2""")
_BLOCK_RE = re.compile(r"\{%-?\s*block\s+(\w+)")
_ENDBLOCK_RE = re.compile(r"\{%-?\s*endblock\b")
REFERENCE_TAGS = frozenset({"extends", "include", "import", "from"})


@dataclass(frozen=True)
class Reference:
    kind: str
    #: The template name, or None when it comes from a variable.
    name: str | None
    offset: int
    token: Token


@dataclass
class Block:
    name: str
    start: int
    content_start: int
    content_end: int
    end: int
    parent: Block | None = None

    def holds(self, offset: int) -> bool:
        return self.content_start <= offset < self.content_end


def references(source_tokens: Iterable[Token]) -> list[Reference]:
    result = []
    for token in source_tokens:
        if token.name not in REFERENCE_TAGS:
            continue
        match = _REFERENCE_RE.match(token.text)
        result.append(Reference(token.name, match.group(3) if match else None, token.offset, token))
    return result


def blocks(source_tokens: Iterable[Token]) -> list[Block]:
    found: list[Block] = []
    stack: list[Block] = []
    for token in source_tokens:
        if token.name == "block":
            match = _BLOCK_RE.match(token.text)
            if not match:
                continue
            block = Block(
                name=match.group(1),
                start=token.offset,
                content_start=token.offset + len(token.text),
                content_end=-1,
                end=-1,
                parent=stack[-1] if stack else None,
            )
            stack.append(block)
            found.append(block)
        elif token.name == "endblock" and stack and _ENDBLOCK_RE.match(token.text):
            block = stack.pop()
            block.content_end = token.offset
            block.end = token.offset + len(token.text)
    for block in stack:  # unclosed blocks run to the end of the file
        block.content_end = block.end = 10**12
    return found


class ParsedTemplate:
    """A template file, parsed lazily and at most once."""

    def __init__(self, path: Path, source: str) -> None:
        self.path = path
        self.source = source

    @cached_property
    def tokens(self) -> list[Token]:
        return tokens(self.source)

    @cached_property
    def references(self) -> list[Reference]:
        return references(self.tokens)

    @cached_property
    def blocks(self) -> list[Block]:
        return blocks(self.tokens)

    @cached_property
    def root(self) -> dom.Node:
        prepared = prepare(self.source)
        return dom.parse(prepared.html, branch_of=prepared.branches.at, source=self.source)

    @cached_property
    def _line_starts(self) -> list[int]:
        text = strip_comments(self.source)
        return [0] + [i + 1 for i, char in enumerate(text) if char == "\n"]

    @property
    def extends(self) -> Reference | None:
        return next((r for r in self.references if r.kind == "extends"), None)

    def block(self, name: str) -> Block | None:
        return next((b for b in self.blocks if b.name == name), None)

    def offset(self, line: int, col: int) -> int:
        return self._line_starts[line - 1] + col - 1

    def position(self, offset: int) -> tuple[int, int]:
        index = bisect_right(self._line_starts, offset) - 1
        return index + 1, offset - self._line_starts[index] + 1

    def block_at(self, offset: int) -> Block | None:
        """The innermost block whose content contains ``offset``."""
        inner = None
        for block in self.blocks:
            if block.holds(offset) and (inner is None or block.start > inner.start):
                inner = block
        return inner

    def top_block_at(self, offset: int) -> Block | None:
        block = self.block_at(offset)
        while block is not None and block.parent is not None:
            block = block.parent
        return block

    def name_of(self) -> str:
        return self.path.name


class TemplateIndex:
    """Maps template names to files the way Django's loaders do: the first
    folder that has the file wins."""

    def __init__(self, dirs: Iterable[Path], extensions: Iterable[str]) -> None:
        self.dirs = list(dict.fromkeys(Path(d).resolve() for d in dirs))
        self.extensions = tuple(e.lower() for e in extensions)
        self._cache: dict[Path, ParsedTemplate | None] = {}
        self._found: dict[str, Path | None] = {}

    def find(self, name: str) -> Path | None:
        if name not in self._found:
            path = None
            if not name.startswith("/") and ".." not in Path(name).parts:
                for directory in self.dirs:
                    candidate = directory / name
                    if candidate.is_file():
                        path = candidate.resolve()
                        break
            self._found[name] = path
        return self._found[name]

    def load(self, path: Path) -> ParsedTemplate | None:
        path = path.resolve()
        if path not in self._cache:
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self._cache[path] = None
            else:
                self._cache[path] = ParsedTemplate(path, source)
        return self._cache[path]

    def get(self, name: str) -> ParsedTemplate | None:
        path = self.find(name)
        return self.load(path) if path is not None else None

    def name_of(self, path: Path) -> str | None:
        path = path.resolve()
        for directory in self.dirs:
            try:
                return path.relative_to(directory).as_posix()
            except ValueError:
                continue
        return None

    def files(self) -> Iterator[Path]:
        for directory in self.dirs:
            for dirpath, dirnames, filenames in os.walk(directory):
                dirnames.sort()
                for filename in sorted(filenames):
                    if filename.lower().endswith(self.extensions):
                        yield Path(dirpath) / filename

    @cached_property
    def extended(self) -> set[str]:
        """Names of templates that another template extends (layouts, not pages)."""
        names: set[str] = set()
        for path in self.files():
            template = self.load(path)
            if template is not None and template.extends and template.extends.name:
                names.add(template.extends.name)
        return names

    def chain(self, template: ParsedTemplate, limit: int = 10) -> list[ParsedTemplate]:
        """The templates ``template`` extends, nearest first; stops at an
        unresolvable or circular ``{% extends %}``."""
        result: list[ParsedTemplate] = []
        seen = {template.path}
        current = template
        while len(result) < limit:
            reference = current.extends
            if reference is None or reference.name is None:
                break
            parent = self.get(reference.name)
            if parent is None or parent.path in seen:
                return []  # unknown or circular: do not guess
            result.append(parent)
            seen.add(parent.path)
            current = parent
        return result
