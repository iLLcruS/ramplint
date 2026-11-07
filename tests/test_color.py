"""Colour parsing, compositing and WCAG contrast ratios."""

from __future__ import annotations

import random

import pytest

from ramplint.browser.color import (
    WHITE,
    Color,
    composite,
    contrast_ratio,
    is_large_text,
    luminance,
    parse_color,
)


def reference_ratio(fg: tuple[float, float, float, float], bg: tuple[float, float, float]) -> float:
    """Straight from the WCAG 2.2 definitions, written independently of ramplint."""

    def linear(channel: float) -> float:
        s = channel / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    def lum(rgb: tuple[float, float, float]) -> float:
        r, g, b = (linear(c) for c in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    alpha = fg[3]
    blended = tuple(fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3))
    high, low = sorted((lum(blended), lum(bg)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def colour_pairs(count: int = 50) -> list[tuple[tuple[float, ...], tuple[float, ...]]]:
    rng = random.Random(2026)
    pairs = []
    for index in range(count):
        fg = tuple(rng.randrange(256) for _ in range(3))
        bg = tuple(rng.randrange(256) for _ in range(3))
        alpha = 1.0 if index % 3 else rng.choice([0.25, 0.5, 0.75, 0.9])
        pairs.append(((*fg, alpha), bg))
    return pairs


@pytest.mark.parametrize("fg, bg", colour_pairs(), ids=[f"pair{i}" for i in range(50)])
def test_matches_the_reference_on_50_pairs(fg, bg):
    ours = contrast_ratio(Color(*fg), Color(*bg))
    assert ours == pytest.approx(reference_ratio(fg, bg), abs=0.005)


@pytest.mark.parametrize(
    "fg, bg, expected",
    [
        # Values published by the WebAIM contrast checker.
        ("rgb(0, 0, 0)", "rgb(255, 255, 255)", 21.0),
        ("rgb(255, 255, 255)", "rgb(255, 255, 255)", 1.0),
        ("rgb(118, 118, 118)", "rgb(255, 255, 255)", 4.54),
        ("rgb(119, 119, 119)", "rgb(255, 255, 255)", 4.48),
        ("rgb(0, 0, 255)", "rgb(255, 255, 255)", 8.59),
        ("rgb(255, 0, 0)", "rgb(255, 255, 255)", 3.99),
        ("rgb(0, 128, 0)", "rgb(255, 255, 255)", 5.14),
        ("rgb(128, 128, 128)", "rgb(255, 255, 255)", 3.95),
    ],
)
def test_known_ratios(fg, bg, expected):
    ratio = contrast_ratio(parse_color(fg), parse_color(bg))
    assert ratio == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("rgb(1, 2, 3)", Color(1, 2, 3)),
        ("rgba(1, 2, 3, 0.5)", Color(1, 2, 3, 0.5)),
        ("rgb(1 2 3 / 50%)", Color(1, 2, 3, 0.5)),
        ("color(srgb 1 0 0.5)", Color(255, 0, 127.5)),
        ("color(srgb 0 0 0 / 0.25)", Color(0, 0, 0, 0.25)),
        ("transparent", Color(0, 0, 0, 0)),
        ("oklch(0.5 0.1 200)", None),
        ("red", None),
    ],
)
def test_parse_color(value, expected):
    assert parse_color(value) == expected


def test_composite_and_alpha():
    half_black = Color(0, 0, 0, 0.5)
    assert composite([half_black]).hex == "#808080"
    assert composite([half_black, Color(255, 0, 0)]).hex == "#800000"
    assert composite([]) == WHITE
    # A transparent background is painted on the white page first.
    assert contrast_ratio(Color(0, 0, 0), Color(0, 0, 0, 0)) == pytest.approx(21)
    assert Color(10, 20, 30).with_alpha(0.5).a == 0.5
    assert luminance(WHITE) == pytest.approx(1)


@pytest.mark.parametrize(
    "size, weight, large",
    [(24, 400, True), (23.9, 400, False), (18.66, 700, True), (18.66, 600, False), (19, 800, True)],
)
def test_large_text(size, weight, large):
    assert is_large_text(size, weight) is large
