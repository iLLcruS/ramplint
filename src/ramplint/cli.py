from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ramplint import __version__
from ramplint.config import ConfigError, load_config
from ramplint.linter import DEFAULT_EXTENSIONS, Violation, iter_template_files, lint_file
from ramplint.reporters import report_github, report_json, report_text
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
        choices=("text", "json", "github"),
        default=None,
        help="output format (default: text, or github when running in GitHub Actions)",
    )
    parser.add_argument("--config", type=Path, metavar="PATH", help="path to a pyproject.toml")
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_rules:
        _list_rules()
        return EXIT_OK

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

    output_format = args.format or (
        "github" if os.environ.get("GITHUB_ACTIONS") == "true" else "text"
    )
    try:
        if output_format == "json":
            report_json(violations, files_checked, sys.stdout)
        elif output_format == "github":
            report_github(violations, files_checked, sys.stdout)
        else:
            report_text(violations, files_checked, sys.stdout, color=_use_color(args.no_color))
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
