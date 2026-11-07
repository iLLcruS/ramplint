"""Colours and contrast, as WCAG 2.2 defines them.

Computed styles give colours as ``rgb()`` / ``rgba()`` (and ``color(srgb ...)``
in some cases). Semi-transparent colours are composited over what lies behind
them before the contrast ratio is computed.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_RGB_RE = re.compile(
    r"^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$", re.I
)
_SRGB_RE = re.compile(
    r"^color\(\s*srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*/\s*([\d.]+%?))?\s*\)$", re.I
)


@dataclass(frozen=True)
class Color:
    """sRGB with channels 0-255 and alpha 0-1."""

    r: float
    g: float
    b: float
    a: float = 1.0

    @property
    def hex(self) -> str:
        return "#{:02x}{:02x}{:02x}".format(*(round(c) for c in (self.r, self.g, self.b)))

    def over(self, background: Color) -> Color:
        """This colour painted over an opaque ``background``."""
        a = self.a
        return Color(
            self.r * a + background.r * (1 - a),
            self.g * a + background.g * (1 - a),
            self.b * a + background.b * (1 - a),
        )

    def with_alpha(self, factor: float) -> Color:
        return Color(self.r, self.g, self.b, self.a * factor)


WHITE = Color(255, 255, 255)


def _alpha(value: str | None) -> float:
    if value is None:
        return 1.0
    return float(value[:-1]) / 100 if value.endswith("%") else float(value)


def parse_color(value: str) -> Color | None:
    """A computed CSS colour, or ``None`` for formats ramplint does not read."""
    value = value.strip()
    if value == "transparent":
        return Color(0, 0, 0, 0)
    match = _RGB_RE.match(value)
    if match:
        r, g, b = (float(match.group(i)) for i in (1, 2, 3))
        return Color(r, g, b, _alpha(match.group(4)))
    match = _SRGB_RE.match(value)
    if match:
        r, g, b = (float(match.group(i)) * 255 for i in (1, 2, 3))
        return Color(r, g, b, _alpha(match.group(4)))
    return None


def _channel(value: float) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(color: Color) -> float:
    """Relative luminance of an opaque colour."""
    return 0.2126 * _channel(color.r) + 0.7152 * _channel(color.g) + 0.0722 * _channel(color.b)


def contrast_ratio(foreground: Color, background: Color) -> float:
    """WCAG contrast ratio (1 to 21); ``foreground`` may be transparent."""
    background = background if background.a >= 1 else background.over(WHITE)
    foreground = foreground.over(background) if foreground.a < 1 else foreground
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def composite(backgrounds: Sequence[Color]) -> Color:
    """Backgrounds listed from the element outwards, painted onto the white page."""
    result = WHITE
    for color in reversed(backgrounds):
        result = color.over(result)
    return result


def is_large_text(font_size: float, font_weight: int) -> bool:
    """WCAG large text: 18pt (24px), or 14pt (18.66px) and bold."""
    return font_size >= 24 or (font_size >= 18.66 and font_weight >= 700)
