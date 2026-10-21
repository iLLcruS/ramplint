"""Landmark rules (RL306)."""

from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import RAW_TEXT_ELEMENTS, Node
from ramplint.rules.aria import effective_role
from ramplint.rules.base import rule
from ramplint.template import may_render_markup, mutually_exclusive

_NOT_CONTENT = RAW_TEXT_ELEMENTS | {"head"}


def _is_main(node: Node) -> bool:
    if node.is_dynamic("role"):
        return node.tag == "main"
    role = effective_role(node)
    if role is not None:
        return role == "main"
    return node.tag == "main"


def _may_be_main(node: Node) -> bool:
    """A main landmark may come from attributes rendered at runtime."""
    return node.dynamic_attrs or node.is_dynamic("role")


def _has_visible_text(node: Node) -> bool:
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                return True
        elif child.tag not in _NOT_CONTENT and child.text().strip():
            return True
    return False


def _main_inside_parent_main(root: Node) -> Iterator[tuple[Node, str]]:
    """A <main> in a block that the parent template already wraps in <main>."""
    context = root.context
    if context is None or not context.extends_known:
        return
    for node in root.iter():
        if node.inert or not _is_main(node) or "hidden" in node.attrs:
            continue
        block = context.template.top_block_at(context.template.offset(node.line, node.col))
        if block is None:
            continue
        found = context.main_around(block.name)
        if found is None:
            continue
        parent, line = found
        yield (
            node,
            f"{parent.path.name} already wraps the {block.name!r} block in <main> (line "
            f"{line}), so the page gets two main landmarks; use <div> or <section> here",
        )


@rule(
    code="RL306",
    name="landmark-one-main",
    summary="A page must have exactly one main landmark.",
    wcag="1.3.1 Info and Relationships (A), 2.4.1 Bypass Blocks (A)",
)
def landmark_one_main(root: Node) -> Iterator[tuple[Node, str]]:
    yield from _main_inside_parent_main(root)
    mains: list[Node] = []
    may_have_main = may_render_markup(root.text())
    for node in root.iter():
        if node.inert:
            continue
        if _may_be_main(node):
            may_have_main = True
        # Extra <main hidden> elements are allowed (e.g. inactive app views).
        if not _is_main(node) or "hidden" in node.attrs:
            continue
        clash = next(
            (other for other in mains if not mutually_exclusive(other.branch, node.branch)),
            None,
        )
        mains.append(node)
        if clash is not None:
            yield (
                node,
                f"Second main landmark (the first is on line {clash.line}); a page must "
                'have one <main> so "skip to content" and landmark navigation work. '
                "Use <section> or <div> here, or add the hidden attribute",
            )

    if mains or may_have_main:
        return
    html = next(root.iter("html"), None)
    if html is None:
        return  # a partial or a child template: the main may be elsewhere
    body = next(html.iter("body"), None)
    if not _has_visible_text(body or html):
        return  # e.g. a page that only runs a script and closes itself
    yield (
        body or html,
        "Page has no main landmark; wrap the main content in <main> so screen reader "
        "users can jump straight to it",
    )
