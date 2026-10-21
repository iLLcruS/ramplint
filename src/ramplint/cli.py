from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ramplint import __version__
from ramplint.config import ConfigError, load_config
from ramplint.linter import DEFAULT_EXCLUDE_DIRS, DEFAULT_EXTENSIONS, Violation, lint_file
from ramplint.project.discovery import SettingsNotFound
from ramplint.project.listing import describe_projects, print_verbose
from ramplint.project.workspace import Workspace
from ramplint.reporters import (
    REPORTERS,
    STATISTICS_WRITERS,
    WriteReport,
    available_formats,
    summary_line,
)
from ramplint.rules import all_rules, find_rule, rule_docs, select_rules, unknown_selectors

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
        "paths",
        nargs="*",
        help=(
            "files or directories to lint (default: the template folders of the Django "
            "project in the current directory, or every template under it)"
        ),
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
        "--settings",
        metavar="MODULE",
        help="Django settings module to read template folders from (e.g. config.settings.base)",
    )
    parser.add_argument(
        "--no-django",
        action="store_true",
        help="do not look for Django projects; lint every template under the given paths",
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="show the Django project, settings and template folders ramplint uses, and exit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print the projects, settings and template folders used to stderr",
    )
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
    parser.add_argument(
        "--explain",
        metavar="RULE",
        help="show the documentation of a rule (code or name, e.g. RL101 or img-alt) and exit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _list_rules() -> None:
    rules = all_rules()
    width = max(len(rule.name) for rule in rules)
    for rule in rules:
        print(f"{rule.code}  {rule.name:<{width}}  {rule.summary}  [WCAG {rule.wcag}]")


def _explain(selector: str) -> int:
    rule = find_rule(selector)
    if rule is None:
        print(f"ramplint: error: unknown rule: {selector}", file=sys.stderr)
        return EXIT_ERROR
    docs = rule_docs(rule)
    if docs is None:
        print(f"{rule.code} {rule.name}: {rule.summary}\nWCAG {rule.wcag}\n{rule.docs_url}")
    else:
        print(docs.rstrip())
        print(f"\nOnline: {rule.docs_url}")
    return EXIT_OK


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
    if args.explain:
        return _explain(args.explain)

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

    settings = args.settings or config.django_settings
    settings_source = "--settings" if args.settings else "pyproject.toml"
    workspace = Workspace(
        extensions=extensions,
        exclude=exclude,
        skip_dirs=DEFAULT_EXCLUDE_DIRS,
        django=config.django and not args.no_django,
        settings=settings,
        settings_source=settings_source if settings else None,
        template_dirs=config.template_dirs,
        config_root=config.source.parent if config.source else None,
    )

    try:
        files = list(workspace.files(args.paths))
    except FileNotFoundError as exc:
        print(f"ramplint: error: no such file or directory: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except SettingsNotFound as exc:
        print(f"ramplint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.list_templates:
        if args.format not in (None, "text", "json"):
            print(
                "ramplint: error: --list-templates works with --format text or json",
                file=sys.stderr,
            )
            return EXIT_ERROR
        describe_projects(workspace, args.paths, files, args.format or "text", sys.stdout)
        return EXIT_OK
    if args.verbose:
        print_verbose(workspace, files, sys.stderr)

    violations: list[Violation] = []
    files_checked = 0
    for path in files:
        files_checked += 1
        violations.extend(lint_file(path, rules, context=workspace.context_for(path)))

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
