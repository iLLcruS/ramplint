from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.template import MARKUP, PLACEHOLDERS

_STRUCTURAL = frozenset({"table", "thead", "tbody", "tfoot", "tr"})


def _own_nodes(table: Node) -> Iterator[Node]:
    """Descendants of ``table`` that are not inside a nested table."""
    for child in table.children:
        if isinstance(child, Node):
            yield child
            if child.tag != "table":
                yield from _own_nodes(child)


def _is_dynamic(table: Node) -> bool:
    """Rows or cells are rendered by something we cannot see.

    Examples: ``{% include "rows.html" %}``, ``{% block rows %}`` or
    ``{{ form.as_table }}`` placed directly between table tags.
    """
    if MARKUP in table.text():
        return True
    for node in (table, *_own_nodes(table)):
        if node.tag not in _STRUCTURAL:
            continue
        for child in node.children:
            if isinstance(child, str) and any(p in child for p in PLACEHOLDERS):
                return True
    return False


@rule(
    code="RL201",
    name="table-header",
    summary="Data tables must use <th> header cells.",
    wcag="1.3.1 Info and Relationships (A)",
)
def table_header(root: Node) -> Iterator[tuple[Node, str]]:
    for table in root.iter("table"):
        if table.role in ("presentation", "none"):
            continue
        if any(node.tag == "th" for node in _own_nodes(table)):
            continue
        if _is_dynamic(table):
            continue
        yield (
            table,
            (
                '<table> has no <th> header cells; mark up headers with <th scope="col"> '
                '/ <th scope="row"> (or add role="presentation" to a layout table)'
            ),
        )
