from __future__ import annotations

import re
from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.template import PLACEHOLDERS


@rule(
    code="RL601",
    name="html-lang",
    summary="The <html> element must declare the page language.",
    wcag="3.1.1 Language of Page (A)",
)
def html_lang(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("html"):
        if node.dynamic_attrs or node.has_value("lang"):
            continue
        yield (
            node,
            (
                '<html> is missing a lang attribute; add e.g. lang="en" or '
                'lang="{{ LANGUAGE_CODE }}"'
            ),
        )


_VIEWPORT_SPLIT_RE = re.compile(r"[,;]")
_DISABLED_SCALING = frozenset({"no", "0", "false"})
#: WCAG 1.4.4 requires text to be resizable up to 200 %.
_MIN_MAXIMUM_SCALE = 2.0


def _viewport_settings(content: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    for part in _VIEWPORT_SPLIT_RE.split(content):
        key, sep, value = part.partition("=")
        if sep:
            settings[key.strip().lower()] = value.strip().lower()
    return settings


@rule(
    code="RL602",
    name="viewport-zoom",
    summary="The viewport meta tag must not disable zooming.",
    wcag="1.4.4 Resize Text (AA)",
)
def viewport_zoom(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("meta"):
        if (node.get("name") or "").strip().lower() != "viewport":
            continue
        settings = _viewport_settings(node.get("content") or "")
        problems: list[str] = []

        scalable = settings.get("user-scalable")
        if scalable is not None and scalable in _DISABLED_SCALING:
            problems.append(f"user-scalable={scalable} disables zooming")

        maximum = settings.get("maximum-scale")
        if maximum is not None and not any(p in maximum for p in PLACEHOLDERS):
            try:
                # Zero or negative values are invalid and ignored by browsers.
                if 0 < float(maximum) < _MIN_MAXIMUM_SCALE:
                    problems.append(f"maximum-scale={maximum} limits zoom below 200%")
            except ValueError:
                pass

        if problems:
            yield (
                node,
                f"Viewport meta tag: {'; '.join(problems)}. Users must be able to "
                "zoom; remove these settings",
            )
