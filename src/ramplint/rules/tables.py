from __future__ import annotations

import difflib
from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.rules.names import has_accessible_name
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


_SCOPE_VALUES = ("row", "col", "rowgroup", "colgroup")
_SCOPE_TYPOS = {"column": "col", "columns": "col", "cols": "col", "rows": "row"}


def _scope_suggestion(value: str) -> str:
    match = _SCOPE_TYPOS.get(value) or next(
        iter(difflib.get_close_matches(value, _SCOPE_VALUES, n=1, cutoff=0.6)), None
    )
    return f'; did you mean scope="{match}"?' if match else ""


@rule(
    code="RL202",
    name="th-scope",
    summary="scope must be row, col, rowgroup or colgroup, and only used on <th>.",
    wcag="1.3.1 Info and Relationships (A)",
)
def th_scope(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("th", "td"):
        value = node.get("scope")
        if value is None or node.is_dynamic("scope"):
            continue
        if node.tag == "td":
            yield (
                node,
                "scope only works on <th>; screen readers ignore it on <td>. Make the "
                "header cell a <th>",
            )
            continue
        normalized = value.strip().lower()
        if normalized in _SCOPE_VALUES:
            continue
        yield (
            node,
            f'scope="{value.strip()}" is not valid; use row, col, rowgroup or colgroup'
            f"{_scope_suggestion(normalized)}",
        )


def _rows(table: Node) -> list[Node]:
    return [node for node in _own_nodes(table) if node.tag == "tr"]


def _cells(row: Node) -> list[Node]:
    return [c for c in row.children if isinstance(c, Node) and c.tag in ("td", "th")]


def _starts_with_header(row: Node) -> bool:
    cells = _cells(row)
    return bool(cells) and cells[0].tag == "th"


def _is_corner_cell(cell: Node, table: Node) -> bool:
    """Top-left cell of a table with both column and row headers."""
    rows = _rows(table)
    if not rows or cell.parent is not rows[0]:
        return False
    cells = _cells(rows[0])
    if not cells or cells[0] is not cell:
        return False
    return any(_starts_with_header(row) for row in rows[1:])


def _nearest_table(node: Node) -> Node | None:
    return next((a for a in node.ancestors() if a.tag == "table"), None)


@rule(
    code="RL203",
    name="empty-table-header",
    summary="Table header cells must have text.",
    wcag="1.3.1 Info and Relationships (A)",
)
def empty_table_header(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("th"):
        if node.aria_hidden or has_accessible_name(node):
            continue
        table = _nearest_table(node)
        if table is not None:
            if table.role in ("presentation", "none"):
                continue
            if _is_corner_cell(node, table):
                continue
        yield (
            node,
            "<th> is empty, so screen readers announce a blank header for its whole "
            "column or row; add text (it can be visually hidden), or use <td> for an "
            "empty cell",
        )
