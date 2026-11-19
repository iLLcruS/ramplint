from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ramplint import __version__
from ramplint.browser.command import BROWSER_OPTIONS, add_browser_arguments, run_browser
from ramplint.browser.options import is_url
from ramplint.config import Config, ConfigError, load_config
from ramplint.exit_codes import EXIT_ERROR, EXIT_INTERRUPTED, EXIT_OK, EXIT_VIOLATIONS
from ramplint.linter import DEFAULT_EXCLUDE_DIRS, DEFAULT_EXTENSIONS, Violation
from ramplint.project.discovery import SettingsNotFound
from ramplint.project.listing import describe_projects, describe_urls, print_verbose
from ramplint.project.urls import project_urlconf
from ramplint.project.workspace import Workspace
from ramplint.reporters import (
    REPORTERS,
    STATISTICS_WRITERS,
    WriteReport,
    available_formats,
    baseline_report,
    summary_line,
)
from ramplint.rules import (
    Rule,
    all_rules,
    find_rule,
    rule_docs,
    select_rules,
    unknown_selectors,
)

__all__ = ["EXIT_ERROR", "EXIT_INTERRUPTED", "EXIT_OK", "EXIT_VIOLATIONS", "build_parser", "main"]


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
            "project in the current directory, or every template under it), or URLs "
            "(http://, https://) of a running site to check in a browser"
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
        "--list-urls",
        action="store_true",
        help="show the URL patterns of the Django project (read from ROOT_URLCONF), and exit",
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
    parser.add_argument(
        "--fix",
        action="store_true",
        help="fix problems with one obvious fix in place (scope, autocomplete, tabindex, "
        "viewport and lang values), then report the rest",
    )
    parser.add_argument(
        "--changed",
        nargs="?",
        const="HEAD",
        metavar="REF",
        help="lint only the files changed since the git commit REF (e.g. origin/main), "
        "including uncommitted and untracked files (default REF: HEAD)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        metavar="SCAN_JSON",
        help="compare with an earlier --write-baseline file (or a browser scan.json): "
        "report only new problems and fail only on them",
    )
    parser.add_argument(
        "--write-baseline",
        type=Path,
        metavar="FILE",
        help="write the problems found to FILE, to use with --baseline later",
    )
    parser.add_argument("--list-rules", action="store_true", help="list available rules and exit")
    parser.add_argument(
        "--explain",
        metavar="RULE",
        help="show the documentation of a rule (code or name, e.g. RL101 or img-alt) and exit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    add_browser_arguments(parser)
    return parser


def _list_rules() -> None:
    rules = all_rules()
    width = max(len(rule.name) for rule in rules)
    for rule in rules:
        browser = "  [browser]" if rule.browser_only else ""
        print(f"{rule.code}  {rule.name:<{width}}  {rule.summary}  [WCAG {rule.wcag}]{browser}")


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

    urls = [p for p in args.paths if is_url(p)]
    if args.fix and (urls or args.runserver):
        print("ramplint: error: --fix works with templates, not URLs", file=sys.stderr)
        return EXIT_ERROR
    if args.changed is not None and (urls or args.runserver):
        print("ramplint: error: --changed works with templates, not URLs", file=sys.stderr)
        return EXIT_ERROR
    used = [name for name in BROWSER_OPTIONS if getattr(args, name) is not None]
    base_url = config.browser.get("base_url")
    if args.runserver:
        if args.paths:
            print(
                "ramplint: error: --runserver scans the project in this folder; "
                "do not pass paths or URLs",
                file=sys.stderr,
            )
            return EXIT_ERROR
        return run_browser(args, [], rules, config, _workspace(args, config), _write_output)
    if not args.paths and used and base_url:
        # ``ramplint --viewport mobile`` with ``base-url`` in the config.
        urls = [base_url]
    if urls:
        if args.paths and len(urls) != len(args.paths):
            print("ramplint: error: pass either URLs or files, not both", file=sys.stderr)
            return EXIT_ERROR
        if args.list_templates:
            print("ramplint: error: --list-templates does not work with URLs", file=sys.stderr)
            return EXIT_ERROR
        return run_browser(args, urls, rules, config, _workspace(args, config), _write_output)
    if used:
        flag = "--" + used[0].replace("_", "-")
        print(
            f"ramplint: error: {flag} needs URLs to check in a browser "
            "(or base-url in [tool.ramplint.browser])",
            file=sys.stderr,
        )
        return EXIT_ERROR

    workspace = _workspace(args, config)
    if args.list_urls:
        return _list_urls(args, workspace)

    try:
        files = list(workspace.files(args.paths))
    except FileNotFoundError as exc:
        print(f"ramplint: error: no such file or directory: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except SettingsNotFound as exc:
        print(f"ramplint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.changed is not None and args.write_baseline is not None:
        print(
            "ramplint: error: --write-baseline needs every file; do not use it with --changed",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if args.changed is not None and not args.list_templates:
        from ramplint.changed import ChangedFilesError, changed_files, only_changed

        try:
            files = only_changed(files, changed_files(args.changed))
        except ChangedFilesError as exc:
            print(f"ramplint: error: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if args.verbose:
            print(f"ramplint: {len(files)} changed files since {args.changed}", file=sys.stderr)

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

    if args.fix and not _fix_files(files, rules):
        return EXIT_ERROR
    checked = {path.as_posix() for path in files} if args.changed is not None else None
    return _lint_templates(args, workspace.lint(files, rules), len(files), checked)


def _fix_files(files: list[Path], rules: list[Rule]) -> bool:
    """``--fix``: rewrite the templates in place; False if one cannot be written."""
    from ramplint.fix import fix_source

    fixed = changed = 0
    for path in files:
        if path.suffix == ".py":
            continue
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                source = fh.read()
        except (OSError, UnicodeDecodeError):
            continue  # linting reports what it can read
        new_source, fixes = fix_source(source, rules)
        if not fixes or new_source == source:
            continue
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(new_source)
        except OSError as exc:
            print(f"ramplint: error: cannot write {path}: {exc}", file=sys.stderr)
            return False
        fixed += len(fixes)
        changed += 1
    if fixed:
        plural = "s" if fixed != 1 else ""
        files_word = "file" if changed == 1 else "files"
        print(f"ramplint: fixed {fixed} problem{plural} in {changed} {files_word}", file=sys.stderr)
    return True


def _lint_templates(
    args: argparse.Namespace,
    violations: list[Violation],
    files_checked: int,
    checked: set[str] | None = None,
) -> int:
    """Report template problems, compared with ``--baseline`` when it is given.

    ``checked`` (with ``--changed``) limits the baseline to the files linted, so
    problems in files that were not checked are not counted as fixed.
    """
    from ramplint.baselines import write_template_baseline
    from ramplint.browser.baseline import EXISTING, BaselineError, compare, load_baseline

    fixed: list[dict[str, object]] = []
    if args.baseline is not None:
        try:
            baseline = load_baseline(args.baseline)
        except BaselineError as exc:
            print(f"ramplint: error: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if checked is not None:
            baseline = [entry for entry in baseline if entry.get("path") in checked]
        comparison = compare(violations, baseline)
        violations, fixed = comparison.violations, comparison.fixed
        print(
            f"ramplint: compared with {args.baseline}: {len(comparison.new)} new, "
            f"{len(comparison.existing)} existing, {len(fixed)} fixed",
            file=sys.stderr,
        )
    if args.write_baseline is not None:
        try:
            write_template_baseline(args.write_baseline, violations, files_checked)
        except OSError as exc:
            print(
                f"ramplint: error: cannot write baseline {args.write_baseline}: {exc}",
                file=sys.stderr,
            )
            return EXIT_ERROR
        print(
            f"ramplint: baseline with {len(violations)} problems written to {args.write_baseline}",
            file=sys.stderr,
        )
    if args.baseline is None:
        code = _write_output(args, violations, files_checked)
        # Every problem found is in the new baseline: nothing new to fail on.
        return EXIT_OK if args.write_baseline is not None and code != EXIT_ERROR else code

    shown = violations
    text_like = (args.format or "text") in ("text", "github") and not args.statistics
    if text_like and args.output is None:
        shown = [v for v in violations if v.baseline != EXISTING]
        hidden = len(violations) - len(shown)
        if hidden or fixed:
            print(
                f"ramplint: {hidden} existing and {len(fixed)} fixed problems are not shown "
                f"(baseline {args.baseline})",
                file=sys.stderr,
            )
    with baseline_report(fixed):
        code = _write_output(args, shown, files_checked)
    if code == EXIT_ERROR:
        return code
    failing = any(v.baseline != EXISTING for v in violations)
    return EXIT_VIOLATIONS if failing and not args.exit_zero else EXIT_OK


def _workspace(args: argparse.Namespace, config: Config) -> Workspace:
    settings = args.settings or config.django_settings
    settings_source = "--settings" if args.settings else "pyproject.toml"
    return Workspace(
        extensions=args.extensions or config.extensions or list(DEFAULT_EXTENSIONS),
        exclude=[*config.exclude, *args.exclude],
        skip_dirs=DEFAULT_EXCLUDE_DIRS,
        django=config.django and not args.no_django,
        settings=settings,
        settings_source=settings_source if settings else None,
        template_dirs=config.template_dirs,
        config_root=config.source.parent if config.source else None,
    )


def _list_urls(args: argparse.Namespace, workspace: Workspace) -> int:
    if args.format not in (None, "text", "json"):
        print("ramplint: error: --list-urls works with --format text or json", file=sys.stderr)
        return EXIT_ERROR
    start = Path(args.paths[0]) if args.paths else workspace.cwd
    try:
        project = workspace.project_for(start)
    except SettingsNotFound as exc:
        print(f"ramplint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if project is None or project.settings_module is None:
        print("ramplint: error: no Django project found (no manage.py)", file=sys.stderr)
        return EXIT_ERROR
    conf = project_urlconf(project)
    if conf is None:
        print(f"ramplint: error: no ROOT_URLCONF in {project.settings_module}", file=sys.stderr)
        return EXIT_ERROR
    describe_urls(workspace, project, conf, args.format or "text", sys.stdout)
    return EXIT_OK


def _write_output(args: argparse.Namespace, violations: list[Violation], files_checked: int) -> int:
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
