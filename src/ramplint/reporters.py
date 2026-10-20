from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TextIO

from ramplint.linter import Violation

_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_DIM = "\033[2m"


def _paint(text: str, *codes: str, color: bool) -> str:
    return f"{''.join(codes)}{text}{_RESET}" if color else text


def report_text(
    violations: Sequence[Violation], files_checked: int, out: TextIO, color: bool = False
) -> None:
    for v in violations:
        location = _paint(f"{v.path}:{v.line}:{v.col}:", _BOLD, color=color)
        code = _paint(v.code, _RED, _BOLD, color=color)
        name = _paint(f"[{v.name}]", _DIM, color=color)
        out.write(f"{location} {code} {v.message} {name}\n")

    files_word = "file" if files_checked == 1 else "files"
    if violations:
        affected = len({v.path for v in violations})
        problems = "problem" if len(violations) == 1 else "problems"
        summary = (
            f"Found {len(violations)} {problems} in {affected} of {files_checked} {files_word}."
        )
        out.write("\n" + _paint(summary, _RED, _BOLD, color=color) + "\n")
    else:
        out.write(
            _paint(f"All checks passed ({files_checked} {files_word}).", _CYAN, color=color) + "\n"
        )


def report_json(violations: Sequence[Violation], files_checked: int, out: TextIO) -> None:
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


def report_github(violations: Sequence[Violation], files_checked: int, out: TextIO) -> None:
    """GitHub Actions workflow commands - shows problems inline in PR diffs."""
    for v in violations:
        file = _escape_github(v.path, property_value=True)
        title = _escape_github(f"{v.code} {v.name}", property_value=True)
        out.write(
            f"::error file={file},line={v.line},col={v.col},title={title}::"
            f"{_escape_github(v.message)}\n"
        )
    report_text(violations, files_checked, out, color=False)


REPORTERS = {"text": report_text, "json": report_json, "github": report_github}
