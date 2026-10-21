"""List structure rules (RL304, RL305)."""

from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule

#: Elements allowed anywhere inside lists: they render nothing themselves.
_SCRIPT_SUPPORTING = frozenset({"script", "template"})


def _child_elements(node: Node) -> list[Node]:
    return [child for child in node.children if isinstance(child, Node)]


def _keeps_list_semantics(node: Node, *allowed_roles: str) -> bool:
    """The list is exposed as a list: no other role and nothing dynamic."""
    if node.dynamic_attrs or node.is_dynamic("role"):
        return False
    return node.role in ("", *allowed_roles)


def _is_full_page(root: Node) -> bool:
    return next(root.iter("html"), None) is not None


def _has_list_context(
    node: Node,
    containers: frozenset[str],
    *,
    full_page: bool,
    container_role: str = "",
    group: str = "",
) -> bool:
    """``node`` is inside one of ``containers``, or may be at render time."""
    parent = node.parent
    if parent is None or parent.tag == "#document":
        # Top level of a partial: it is included into a list elsewhere.
        return not full_page
    if parent.tag in containers:
        return True
    if parent.dynamic_attrs or parent.is_dynamic("role"):
        return True
    if container_role and parent.role == container_role:
        return True
    grandparent = parent.parent or parent
    if grandparent.tag in containers:
        # A wrong wrapper inside the list; the wrapper itself is reported.
        return True
    # A <div> group of a <dl> at the top level of a partial, included elsewhere.
    return bool(group) and parent.tag == group and grandparent.tag == "#document" and not full_page


# --------------------------------------------------------------------------
# RL304 list-structure
# --------------------------------------------------------------------------

_LISTS = frozenset({"ul", "ol"})
_LIST_ITEM_PARENTS = frozenset({"ul", "ol", "menu"})


@rule(
    code="RL304",
    name="list-structure",
    summary="Lists may only contain <li>, and <li> must be inside a list.",
    wcag="1.3.1 Info and Relationships (A)",
)
def list_structure(root: Node) -> Iterator[tuple[Node, str]]:
    full_page = _is_full_page(root)
    for node in root.iter():
        if node.inert:
            continue
        if node.tag in _LISTS:
            if not _keeps_list_semantics(node, "list"):
                continue
            for child in _child_elements(node):
                if child.tag == "li" or child.tag in _SCRIPT_SUPPORTING:
                    continue
                if child.dynamic_attrs or child.is_dynamic("role") or child.role == "listitem":
                    continue
                yield (
                    child,
                    f"<{child.tag}> cannot be a direct child of <{node.tag}>; screen readers "
                    "count and announce <li> items only. Wrap it in an <li> or move it out "
                    "of the list",
                )
        elif node.tag == "li":
            if _has_list_context(
                node, _LIST_ITEM_PARENTS, full_page=full_page, container_role="list"
            ):
                continue
            yield (
                node,
                "<li> is not inside <ul>, <ol> or <menu>, so it is not announced as a "
                "list item; wrap the items in a <ul> or <ol>",
            )


# --------------------------------------------------------------------------
# RL305 definition-list
# --------------------------------------------------------------------------

_DL_ITEMS = frozenset({"dt", "dd"})
_DL = frozenset({"dl"})


@rule(
    code="RL305",
    name="definition-list",
    summary="<dl> may only contain <dt>, <dd> and <div> groups of them.",
    wcag="1.3.1 Info and Relationships (A)",
)
def definition_list(root: Node) -> Iterator[tuple[Node, str]]:
    full_page = _is_full_page(root)
    for node in root.iter():
        if node.inert:
            continue
        if node.tag == "dl":
            if not _keeps_list_semantics(node):
                continue
            for child in _child_elements(node):
                if child.tag in _DL_ITEMS or child.tag in _SCRIPT_SUPPORTING:
                    continue
                if child.dynamic_attrs:
                    continue
                if child.tag != "div":
                    yield (
                        child,
                        f"<{child.tag}> cannot be a direct child of <dl>; use <dt> for terms "
                        "and <dd> for descriptions (optionally grouped in a <div>)",
                    )
                    continue
                for grandchild in _child_elements(child):
                    if grandchild.tag in _DL_ITEMS or grandchild.tag in _SCRIPT_SUPPORTING:
                        continue
                    if grandchild.dynamic_attrs:
                        continue
                    yield (
                        grandchild,
                        f"<{grandchild.tag}> cannot be inside a <div> group of a <dl>; a "
                        "group may only contain <dt> and <dd>",
                    )
        elif node.tag in _DL_ITEMS:
            if _has_list_context(node, _DL, full_page=full_page, group="div"):
                continue
            yield (
                node,
                f"<{node.tag}> is not inside a <dl>, so the term and its description are "
                "not connected for screen readers; wrap them in a <dl>",
            )
