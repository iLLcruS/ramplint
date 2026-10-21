"""What a template looks like together with the templates it extends and includes.

A :class:`TemplateContext` is attached to the root node of the template being
linted (``root.context``). Rules use it to look beyond the file, and every
helper answers ``None`` ("unknown") rather than guessing when a template
cannot be resolved statically.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from ramplint.dom import Node
from ramplint.project.templates import Block, ParsedTemplate, TemplateIndex
from ramplint.rules.aria import effective_role
from ramplint.template import CHILD_BLOCK, MARKUP, Token

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_MAX_INCLUDE_DEPTH = 10


@dataclass(frozen=True)
class Heading:
    level: int
    template: ParsedTemplate
    line: int

    def describe(self) -> str:
        return f"<h{self.level}> in {self.template.path.name} (line {self.line})"


def _headings(template: ParsedTemplate, root: Node) -> list[tuple[int, Node]]:
    return [
        (template.offset(node.line, node.col), node)
        for node in root.iter(*HEADINGS)
        if not node.inert
    ]


class TemplateContext:
    def __init__(self, template: ParsedTemplate, index: TemplateIndex) -> None:
        self.template = template
        self.index = index

    # -- {% extends %} -----------------------------------------------------
    @cached_property
    def chain(self) -> list[ParsedTemplate]:
        """Parents of this template, nearest first (empty when unknown)."""
        return self.index.chain(self.template)

    @property
    def extends_known(self) -> bool:
        return self.template.extends is not None and bool(self.chain)

    def defining_parent(self, name: str) -> tuple[ParsedTemplate, Block] | None:
        """The nearest parent that renders block ``name``."""
        for parent in self.chain:
            block = parent.block(name)
            if block is not None:
                return parent, block
        return None

    def overrides(self, name: str) -> bool:
        return self.template.block(name) is not None

    def _content_markup(self, template: ParsedTemplate, block: Block) -> bool:
        """The block's content contains ``{{ block.super }}``, includes or tags
        that may render unknown markup."""
        return any(
            token.placeholder in (MARKUP, CHILD_BLOCK)
            and block.holds(token.offset)
            and token.name != "block"
            for token in template.tokens
        )

    # -- RL301 -------------------------------------------------------------
    def heading_before(self, name: str) -> Heading | None | bool:
        """The last heading rendered before block ``name``.

        Returns the :class:`Heading`, ``True`` when no heading comes before it,
        or ``None`` when that cannot be known.
        """
        if not self.extends_known or len(self.chain) != 1:
            return None  # only child -> base for now
        base = self.chain[0]
        target = base.block(name)
        if target is None or target.parent is not None:
            return None
        events: list[tuple[int, Heading | None]] = []

        for offset, node in _headings(base, base.root):
            if offset >= target.start:
                break
            block = base.top_block_at(offset)
            if block is not None and self.overrides(block.name):
                continue  # replaced by this template's content
            events.append((offset, Heading(int(node.tag[1]), base, node.line)))

        for token in base.tokens:
            if token.offset >= target.start:
                break
            if token.name == "block":
                block = next((b for b in base.blocks if b.start == token.offset), None)
                if block is None or block.parent is not None or not self.overrides(block.name):
                    continue  # nested blocks come with their parent block
                own = self.template.block(block.name)
                if own is None or self._content_markup(self.template, own):
                    return None
                for offset, node in _headings(self.template, self.template.root):
                    if own.holds(offset):
                        heading = Heading(int(node.tag[1]), self.template, node.line)
                        events.append((block.start, heading))
                continue
            block = base.top_block_at(token.offset)
            if block is not None and self.overrides(block.name):
                continue
            if token.name == "include":
                included = self._resolve(base, token)
                if included is None or any(t.placeholder == MARKUP for t in included.tokens):
                    return None  # unknown, or it renders more templates
                found = _headings(included, included.root)
                if found:
                    node = found[-1][1]
                    events.append((token.offset, Heading(int(node.tag[1]), included, node.line)))
            elif token.placeholder == MARKUP and token.text.startswith("{{"):
                return None  # e.g. {{ block.super }} or a rendered form

        if not events:
            return True
        events.sort(key=lambda event: event[0])
        return events[-1][1]

    # -- RL603 -------------------------------------------------------------
    def empty_title_block(self) -> tuple[ParsedTemplate, str] | None:
        """``(base, block name)`` when the page title stays empty.

        The base renders ``<title>{% block title %}{% endblock %}</title>``
        with nothing else in it, no template in the chain fills the block, and
        nothing extends this template (it is a page, not a layout).
        """
        if not self.extends_known:
            return None
        base = self.chain[-1]
        html = next(base.root.iter("html"), None)
        title = next((t for t in base.root.iter("title") if not t.inert), None)
        if html is None or title is None or title.end is None:
            return None
        start = base.offset(title.line, title.col)
        end = base.offset(*title.end)
        inside = [b for b in base.blocks if start < b.start < end and b.parent is None]
        if len(inside) != 1:
            return None
        block = inside[0]
        # Text around the block, e.g. "{% block title %}{% endblock %} | Shop".
        around = base.source[start : block.start] + base.source[block.end : end]
        if ">" in around and around.split(">", 1)[1].strip():
            return None
        for template in [self.template, *self.chain]:
            own = template.block(block.name)
            if own is None:
                continue
            content = template.source[own.content_start : own.content_end]
            if content.strip():
                return None
            break
        name = self.index.name_of(self.template.path)
        if name is None or name in self.index.extended:
            return None
        return base, block.name

    # -- RL306 -------------------------------------------------------------
    def main_around(self, name: str) -> tuple[ParsedTemplate, int] | None:
        """``(parent, line)`` of the ``<main>`` a parent wraps block ``name`` in."""
        found = self.defining_parent(name)
        if found is None:
            return None
        parent, block = found
        line, col = parent.position(block.start)
        for node in parent.root.iter():
            if node.inert or not (node.tag == "main" or effective_role(node) == "main"):
                continue
            if node.contains(line, col):
                return parent, node.line
        return None

    # -- RL403 / RL703 -----------------------------------------------------
    def _resolve(self, template: ParsedTemplate, token: Token) -> ParsedTemplate | None:
        reference = next((r for r in template.references if r.offset == token.offset), None)
        if reference is None or reference.name is None:
            return None
        return self.index.get(reference.name)

    def ids_with_includes(self) -> set[str] | None:
        """Ids on the rendered page: this template, what it includes, and the
        templates it extends. None if some markup cannot be read."""
        ids: set[str] = set()
        seen: set[Path] = set()
        if not _collect_ids(self.template, self.index, ids, seen, 0, allow_blocks=False):
            return None
        if self.template.extends is not None:
            if not self.chain:
                return None
            for parent in self.chain:
                if not _collect_ids(parent, self.index, ids, seen, 0, allow_blocks=True):
                    return None
        return ids


def _collect_ids(
    template: ParsedTemplate,
    index: TemplateIndex,
    ids: set[str],
    seen: set[Path],
    depth: int,
    allow_blocks: bool,
) -> bool:
    if template.path in seen:
        return True
    if depth > _MAX_INCLUDE_DEPTH:
        return False
    seen.add(template.path)
    for token in template.tokens:
        if token.placeholder != MARKUP:
            continue
        if token.name == "block" and allow_blocks:
            continue  # filled by the template that extends this one
        if token.name != "include":
            return False  # {% block %} of a base template, {{ form }}, custom tags
        reference = next(r for r in template.references if r.offset == token.offset)
        if reference.name is None:
            return False
        included = index.get(reference.name)
        if included is None:
            return False
        if not _collect_ids(included, index, ids, seen, depth + 1, allow_blocks=False):
            return False
    for node in template.root.iter():
        if node.dynamic_attrs or node.is_dynamic("id"):
            return False
        element_id = (node.get("id") or "").strip()
        if element_id:
            ids.add(element_id)
    return True
