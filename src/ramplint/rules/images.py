from __future__ import annotations

import re
from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.aria import effective_role
from ramplint.rules.base import rule
from ramplint.rules.names import has_naming_attribute, static_text
from ramplint.template import may_render_markup


@rule(
    code="RL101",
    name="img-alt",
    summary="Images must have an alt attribute.",
    wcag="1.1.1 Non-text Content (A)",
)
def img_alt(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("img", "area", "input"):
        if node.dynamic_attrs:
            continue

        if node.tag == "img":
            if (
                "alt" in node.attrs
                or node.has_value("aria-label")
                or node.has_value("aria-labelledby")
            ):
                continue
            yield node, '<img> is missing an alt attribute (use alt="" for decorative images)'

        elif node.tag == "area":
            if node.get("href") is None or node.has_value("alt") or has_naming_attribute(node):
                continue
            yield node, "<area> in an image map needs a non-empty alt attribute"

        elif (node.get("type") or "").strip().lower() == "image":
            if node.has_value("alt") or has_naming_attribute(node):
                continue
            yield node, '<input type="image"> needs a non-empty alt attribute describing the action'


def _svg_title(svg: Node) -> Node | None:
    return next(
        (child for child in svg.children if isinstance(child, Node) and child.tag == "title"),
        None,
    )


@rule(
    code="RL104",
    name="svg-img-alt",
    summary='<svg role="img"> must have an accessible name.',
    wcag="1.1.1 Non-text Content (A)",
)
def svg_img_alt(root: Node) -> Iterator[tuple[Node, str]]:
    for svg in root.iter("svg"):
        if svg.dynamic_attrs or svg.aria_hidden or effective_role(svg) != "img":
            continue
        if has_naming_attribute(svg):
            continue
        title = _svg_title(svg)
        if title is not None and title.text().strip():
            continue
        if may_render_markup(svg.text()):
            continue  # the <title> may come from {% include %}
        yield (
            svg,
            '<svg role="img"> has no accessible name; add a <title> as its first child or '
            'an aria-label, or use aria-hidden="true" for a decorative icon',
        )


_FILE_NAME_RE = re.compile(
    r"^[\w\-. ]*\.(?:png|jpe?g|gif|svg|webp|avif|bmp|ico|tiff?)$", re.IGNORECASE
)
_PLACEHOLDER_WORDS = frozenset(
    {"image", "img", "picture", "photo", "photograph", "graphic", "icon", "spacer", "alt"}
)
_REDUNDANT_PREFIX_RE = re.compile(
    r"^(?:an?\s+|the\s+)?(?:image|picture|photo|photograph|graphic)\s+(?:of|showing)\b",
    re.IGNORECASE,
)
_SPACE_RE = re.compile(r"\s+")
#: Elements (or roles) whose name comes from their text, images included.
_CONTAINERS = ("a", "button", "link")


def _normalized(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip().casefold()


def _redundant_alt(alt: str) -> str | None:
    value = alt.strip()
    if _FILE_NAME_RE.match(value):
        return f'alt="{value}" is a file name; describe what the image shows or does'
    if _normalized(value) in _PLACEHOLDER_WORDS:
        return (
            f'alt="{value}" says nothing about the image; describe it, '
            'or use alt="" if it is decorative'
        )
    if _REDUNDANT_PREFIX_RE.match(value):
        return (
            f'alt="{value}" starts with words screen readers already say ("image"); '
            "describe the content only"
        )
    return None


@rule(
    code="RL107",
    name="image-redundant-alt",
    summary="Image alt text must describe the image, not repeat a file name or nearby text.",
    wcag="1.1.1 Non-text Content (A)",
)
def image_redundant_alt(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("img"):
        alt = node.get("alt")
        if node.dynamic_attrs or alt is None or not alt.strip() or node.is_dynamic("alt"):
            continue
        message = _redundant_alt(alt)
        if message is not None:
            yield node, message
            continue
        container = next(
            (a for a in node.ancestors() if a.tag in _CONTAINERS or a.role in _CONTAINERS),
            None,
        )
        if container is None:
            continue
        text = static_text(container, skip=node)
        if text is not None and _normalized(text) == _normalized(alt):
            element = f"<{container.tag}>"
            yield (
                node,
                f'alt="{alt.strip()}" repeats the text of its {element}, so screen readers '
                'say it twice; use alt="" on the image',
            )
