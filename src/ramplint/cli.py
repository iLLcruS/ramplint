from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ramplint import __version__
from ramplint.browser.options import SCREENSHOT_FORMATS, BrowserOptions, is_url
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
    browser_report,
    summary_line,
)
from ramplint.rules import all_rules, find_rule, rule_docs, select_rules, unknown_selectors

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_ERROR = 2
#: Ctrl+C, the usual 128 + SIGINT.
EXIT_INTERRUPTED = 130


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

    browser = parser.add_argument_group(
        "browser scan",
        "Pass URLs instead of paths to check rendered pages in Chromium. "
        'Needs: pip install "ramplint[browser]" && playwright install chromium',
    )
    browser.add_argument(
        "--viewport",
        type=_csv,
        metavar="SIZES",
        help="comma-separated viewports: desktop, tablet, mobile or WIDTHxHEIGHT "
        "(default: desktop)",
    )
    browser.add_argument(
        "--timeout",
        type=float,
        metavar="SECONDS",
        help="time to wait for one page to load (default: 30)",
    )
    browser.add_argument(
        "--delay", type=int, metavar="MS", help="pause between two pages in milliseconds"
    )
    browser.add_argument(
        "--wait-for",
        metavar="SELECTOR",
        help="CSS selector that must appear before a page is checked",
    )
    browser.add_argument(
        "--headed", action="store_true", default=None, help="show the browser window"
    )
    browser.add_argument(
        "--save-snapshots",
        type=Path,
        metavar="DIR",
        help="save the rendered HTML, element data and screenshots of every page to DIR",
    )
    browser.add_argument(
        "--screenshot-format",
        choices=SCREENSHOT_FORMATS,
        help="image format of screenshots (default: jpeg)",
    )
    browser.add_argument(
        "--max-pages", type=int, metavar="N", help="check at most N pages (default: 50)"
    )
    browser.add_argument(
        "--per-pattern",
        type=int,
        metavar="N",
        help="when crawling, check at most N pages per URL pattern such as /products/<id>/ "
        "(default: 2)",
    )
    browser.add_argument(
        "--include",
        action="append",
        metavar="GLOB",
        help="only check URLs matching GLOB (path like /shop/* or a full URL; repeatable)",
    )
    browser.add_argument(
        "--exclude-url",
        action="append",
        metavar="GLOB",
        help="do not check URLs matching GLOB (repeatable)",
    )
    browser.add_argument(
        "--no-crawl",
        action="store_const",
        const=True,
        default=None,
        help="check only the given URLs, do not follow links",
    )
    return parser


_BROWSER_OPTIONS = (
    "viewport",
    "timeout",
    "delay",
    "wait_for",
    "headed",
    "save_snapshots",
    "screenshot_format",
    "max_pages",
    "per_pattern",
    "include",
    "exclude_url",
    "no_crawl",
)


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

    urls = [p for p in args.paths if is_url(p)]
    used = [name for name in _BROWSER_OPTIONS if getattr(args, name) is not None]
    base_url = config.browser.get("base_url")
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
        return _browser_main(args, urls, rules, config.browser)
    if used:
        flag = "--" + used[0].replace("_", "-")
        print(
            f"ramplint: error: {flag} needs URLs to check in a browser "
            "(or base-url in [tool.ramplint.browser])",
            file=sys.stderr,
        )
        return EXIT_ERROR

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
        if path.suffix == ".py":
            violations.extend(lint_file(path, rules, index=workspace.python_index(path)))
        else:
            violations.extend(lint_file(path, rules, context=workspace.context_for(path)))

    return _write_output(args, violations, files_checked)


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


def _browser_options(args: argparse.Namespace, config_values: dict) -> BrowserOptions:
    """``[tool.ramplint.browser]`` overridden by the command line. Raises ValueError."""
    from ramplint.browser.options import BrowserOptions, parse_viewport

    options = BrowserOptions(**config_values)
    if args.viewport:
        options.viewports = [parse_viewport(v) for v in args.viewport]
    if args.timeout is not None:
        if args.timeout <= 0:
            raise ValueError("--timeout must be above 0")
        options.timeout = args.timeout
    if args.delay is not None:
        if args.delay < 0:
            raise ValueError("--delay must not be negative")
        options.delay = args.delay
    if args.wait_for:
        options.wait_for = args.wait_for
    if args.headed:
        options.headed = True
    if args.save_snapshots is not None:
        options.save_snapshots = str(args.save_snapshots)
    if args.screenshot_format:
        options.screenshot_format = args.screenshot_format
    for name in ("max_pages", "per_pattern"):
        value = getattr(args, name)
        if value is not None:
            if value < 1:
                raise ValueError(f"--{name.replace('_', '-')} must be above 0")
            setattr(options, name, value)
    if args.include:
        options.include = list(args.include)
    if args.exclude_url:
        options.exclude = [*options.exclude, *args.exclude_url]
    if args.no_crawl:
        options.crawl = False
    return options


def _start_urls(urls: list[str], options: BrowserOptions) -> list[str]:
    """The given URLs without duplicates, filtered and capped by the options."""
    result: list[str] = []
    for url in dict.fromkeys(urls):
        if options.denied(url):
            print(f"ramplint: warning: not opening {url}: it matches deny", file=sys.stderr)
        elif not options.allowed(url):
            print(f"ramplint: warning: skipped {url}: excluded by the URL filters", file=sys.stderr)
        else:
            result.append(url)
    if len(result) > options.max_pages:
        print(
            f"ramplint: warning: checking the first {options.max_pages} of {len(result)} URLs "
            "(--max-pages)",
            file=sys.stderr,
        )
        result = result[: options.max_pages]
    return result


def _browser_main(
    args: argparse.Namespace, urls: list[str], rules: list, config_values: dict
) -> int:
    from ramplint.browser.scan import scan
    from ramplint.browser.session import BrowserUnavailable

    try:
        options = _browser_options(args, config_values)
    except ValueError as exc:
        print(f"ramplint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    show_progress = args.verbose or sys.stderr.isatty()

    def progress(index: int, total: int, url: str, viewport: str) -> None:
        if show_progress:
            print(f"[{index}/{total}] {url} ({viewport})", file=sys.stderr)

    urls = _start_urls(urls, options)
    if not urls:
        print("ramplint: error: no URL left to check", file=sys.stderr)
        return EXIT_ERROR

    try:
        result = scan(urls, rules, options, progress)
    except BrowserUnavailable as exc:
        print(f"ramplint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        # The session is already closed (context manager); no traceback.
        print("ramplint: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED

    for snapshot in result.snapshots:
        where = f"{snapshot.url} ({snapshot.viewport})"
        if not snapshot.ok:
            print(f"ramplint: warning: cannot open {where}: {snapshot.error}", file=sys.stderr)
        elif not snapshot.is_html:
            print(
                f"ramplint: warning: skipped {where}: not an HTML page ({snapshot.content_type})",
                file=sys.stderr,
            )
        elif snapshot.status is not None and snapshot.status >= 400:
            print(f"ramplint: warning: {where} returned HTTP {snapshot.status}", file=sys.stderr)
    if not result.pages_checked:
        print("ramplint: error: no page could be checked", file=sys.stderr)
        return EXIT_ERROR

    with browser_report([v.name for v in options.viewports]):
        return _write_output(args, result.violations, result.pages_checked)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
