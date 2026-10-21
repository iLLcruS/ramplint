from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ramplint import __version__
from ramplint.config import ConfigError, load_config
from ramplint.linter import DEFAULT_EXTENSIONS, Violation, iter_template_files, lint_file
from ramplint.reporters import (
    REPORTERS,
    STATISTICS_WRITERS,
    WriteReport,
    available_formats,
    summary_line,
)
from ramplint.rules import all_rules, select_rules, unknown_selectors

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_ERROR = 2


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ramplint",
        description="Accessibility linter for Django and Jinja2 templates.",
    )
    parser.add_argument(
        "paths", nargs="*", default=["."], help="files or directories to lint (default: .)"
    )
    parser.add_argument(
        "--select",
        type=_csv,
        metavar="RULES",
        help="comma-separated rule codes, code prefixes or names to enable (e.g. RL1,link-name)",
    )
    parser.add_argument(
        "--ignore", type=_csv, metavar="RULES", help="comma-separated rules to disable"
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="glob pattern of paths to skip; may be repeated",
    )
    parser.add_argument(
        "--extensions",
        type=_csv,
        metavar="EXTS",
        help=f"file extensions to lint (default: {','.join(DEFAULT_EXTENSIONS)})",
    )
    parser.add_argument(
        "--format",
        choices=available_formats(),
        default=None,
        help="output format (default: text, or github when running in GitHub Actions)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="FILE",
        help="write the report to FILE instead of stdout (missing folders are created)",
    )
    parser.add_argument("--config", type=Path, metavar="PATH", help="path to a pyproject.toml")
    parser.add_argument(
        "--statistics",
        action="store_true",
        help="show the number of problems per rule instead of every problem (text or json)",
    )
    parser.add_argument("--no-color", action="store_true", help="disable colored output")
    parser.add_argument(
        "--exit-zero", action="store_true", help="exit with 0 even if problems are found"
    )
    parser.add_argument("--list-rules", action="store_true", help="list available rules and exit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _list_rules() -> None:
    for rule in all_rules():
        print(f"{rule.code}  {rule.name:<15} {rule.summary}  [WCAG {rule.wcag}]")


def _use_color(no_color: bool) -> bool:
    if no_color or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _silence_stdout() -> None:
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):
        pass


def _write_report_file(
    path: Path,
    output_format: str,
    write: WriteReport,
    violations: list[Violation],
    files_checked: int,
) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            write(violations, files_checked, fh, False)
    except OSError as exc:
        print(f"ramplint: error: cannot write report to {path}: {exc}", file=sys.stderr)
        return False
    print(f"{summary_line(violations, files_checked)} {output_format} report written to {path}")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_rules:
        _list_rules()
        return EXIT_OK

    if args.statistics and args.format not in (None, *STATISTICS_WRITERS):
        supported = " or ".join(sorted(STATISTICS_WRITERS))
        print(
            f"ramplint: error: --statistics works with --format {supported}, not {args.format}",
            file=sys.stderr,
        )
        return EXIT_ERROR

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ramplint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    select = args.select if args.select is not None else config.select
    ignore = (config.ignore or []) + (args.ignore or [])
    unknown = unknown_selectors([*select, *ignore])
    if unknown:
        print(f"ramplint: error: unknown rule(s): {', '.join(unknown)}", file=sys.stderr)
        return EXIT_ERROR
    rules = select_rules(select, ignore)

    extensions = args.extensions or config.extensions or list(DEFAULT_EXTENSIONS)
    exclude = [*config.exclude, *args.exclude]

    violations: list[Violation] = []
    files_checked = 0
    try:
        for path in iter_template_files(args.paths, extensions=extensions, exclude=exclude):
            files_checked += 1
            violations.extend(lint_file(path, rules))
    except FileNotFoundError as exc:
        print(f"ramplint: error: no such file or directory: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.output is not None or args.statistics:
        # Annotations only make sense for the full report on stdout.
        output_format = args.format or "text"
    else:
        output_format = args.format or (
            "github" if os.environ.get("GITHUB_ACTIONS") == "true" else "text"
        )
    write: WriteReport = (
        STATISTICS_WRITERS[output_format] if args.statistics else REPORTERS[output_format].write
    )

    if args.output is not None:
        if not _write_report_file(args.output, output_format, write, violations, files_checked):
            return EXIT_ERROR
    else:
        try:
            write(violations, files_checked, sys.stdout, _use_color(args.no_color))
            sys.stdout.flush()
        except BrokenPipeError:
            # The reader went away (e.g. `ramplint | head`). Silence the error that
            # Python would print while flushing stdout on exit.
            _silence_stdout()

    if violations and not args.exit_zero:
        return EXIT_VIOLATIONS
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
