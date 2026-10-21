"""Output formats.

Every format is a function registered with :func:`reporter`. Adding a new
format means writing one function::

    @reporter("csv", "Comma-separated values")
    def report_csv(violations, files_checked, out, color=False):
        ...

The CLI picks up registered formats automatically (``--format`` choices,
``--output`` support).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

from ramplint.linter import Violation

#: ``write(violations, files_checked, out, color)``
WriteReport = Callable[[Sequence[Violation], int, TextIO, bool], None]


@dataclass(frozen=True)
class Reporter:
    name: str
    description: str
    write: WriteReport


REPORTERS: dict[str, Reporter] = {}


def reporter(name: str, description: str) -> Callable[[WriteReport], WriteReport]:
    """Register a function as an output format."""

    def decorator(func: WriteReport) -> WriteReport:
        if name in REPORTERS:
            raise ValueError(f"Output format {name!r} is already registered")
        REPORTERS[name] = Reporter(name=name, description=description, write=func)
        return func

    return decorator


def available_formats() -> list[str]:
    return sorted(REPORTERS)


def summary_line(violations: Sequence[Violation], files_checked: int) -> str:
    files_word = "file" if files_checked == 1 else "files"
    if not violations:
        return f"All checks passed ({files_checked} {files_word})."
    affected = len({v.path for v in violations})
    problems = "problem" if len(violations) == 1 else "problems"
    return f"Found {len(violations)} {problems} in {affected} of {files_checked} {files_word}."


# -- built-in formats ------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_DIM = "\033[2m"


def _paint(text: str, *codes: str, color: bool) -> str:
    return f"{''.join(codes)}{text}{_RESET}" if color else text


@reporter("text", "Human-readable, one problem per line (default)")
def report_text(
    violations: Sequence[Violation], files_checked: int, out: TextIO, color: bool = False
) -> None:
    for v in violations:
        location = _paint(f"{v.path}:{v.line}:{v.col}:", _BOLD, color=color)
        code = _paint(v.code, _RED, _BOLD, color=color)
        name = _paint(f"[{v.name}]", _DIM, color=color)
        out.write(f"{location} {code} {v.message} {name}\n")

    summary = summary_line(violations, files_checked)
    if violations:
        out.write("\n" + _paint(summary, _RED, _BOLD, color=color) + "\n")
    else:
        out.write(_paint(summary, _CYAN, color=color) + "\n")


@reporter("json", "Machine-readable JSON")
def report_json(
    violations: Sequence[Violation], files_checked: int, out: TextIO, color: bool = False
) -> None:
    json.dump(
        {
            "files_checked": files_checked,
            "violations": [v.to_dict() for v in violations],
        },
        out,
        indent=2,
    )
    out.write("\n")


def _escape_github(value: str, *, property_value: bool = False) -> str:
    value = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if property_value:
        value = value.replace(":", "%3A").replace(",", "%2C")
    return value


@reporter("github", "GitHub Actions annotations shown inline in pull requests")
def report_github(
    violations: Sequence[Violation], files_checked: int, out: TextIO, color: bool = False
) -> None:
    for v in violations:
        file = _escape_github(v.path, property_value=True)
        title = _escape_github(f"{v.code} {v.name}", property_value=True)
        out.write(
            f"::error file={file},line={v.line},col={v.col},title={title}::"
            f"{_escape_github(v.message)}\n"
        )
    report_text(violations, files_checked, out, color=False)


# Formats that live in their own module register themselves on import.
from ramplint import html_report, sarif  # noqa: E402, F401
