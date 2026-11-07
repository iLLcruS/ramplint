"""The browser scan on the command line: ``ramplint http://localhost:8000/``."""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TextIO

from ramplint.browser.auth import Role, roles, save_auth, unprotected_secret
from ramplint.browser.baseline import EXISTING, BaselineError, compare, load_baseline
from ramplint.browser.checks import merge_findings, merge_static
from ramplint.browser.frontier import Coverage, Status, start_urls
from ramplint.browser.options import SCREENSHOT_FORMATS, BrowserOptions, parse_viewport
from ramplint.browser.probes import probes_for
from ramplint.browser.report import (
    EMBED_WARNING_BYTES,
    ScreenshotStore,
    scan_data,
    write_folder,
    write_scan_json,
    write_single,
)
from ramplint.browser.scan import ScanResult
from ramplint.config import Config
from ramplint.exit_codes import EXIT_ERROR, EXIT_INTERRUPTED, EXIT_OK, EXIT_VIOLATIONS
from ramplint.linter import Violation
from ramplint.project.discovery import Project, SettingsNotFound
from ramplint.project.urls import UrlConf, project_urlconf
from ramplint.project.workspace import Workspace
from ramplint.reporters import browser_report
from ramplint.rules import Rule

#: Writes the report and returns the exit code: ``(args, violations, pages)``.
WriteOutput = Callable[[argparse.Namespace, list[Violation], int], int]

#: Destinations of the browser options; using one without URLs is an error.
BROWSER_OPTIONS = (
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
    "concurrency",
    "max_states",
    "runserver",
    "auth",
    "save_auth",
    "embed_screenshots",
    "baseline",
    "write_baseline",
)

#: Where Django sends users who must log in, unless ``LOGIN_URL`` says otherwise.
DEFAULT_LOGIN_PATH = "/accounts/login/"


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def add_browser_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group(
        "browser scan",
        "Pass URLs instead of paths to check rendered pages in Chromium. "
        'Needs: pip install "ramplint[browser]" && playwright install chromium',
    )
    add = group.add_argument
    add(
        "--viewport",
        type=_csv,
        metavar="SIZES",
        help="comma-separated viewports: desktop, tablet, mobile or WIDTHxHEIGHT "
        "(default: desktop)",
    )
    add("--timeout", type=float, metavar="SECONDS", help="time to wait for one page (default: 30)")
    add("--delay", type=int, metavar="MS", help="pause between two pages in milliseconds")
    add("--wait-for", metavar="SELECTOR", help="CSS selector that must appear before checking")
    add("--headed", action="store_true", default=None, help="show the browser window")
    add(
        "--save-snapshots",
        type=Path,
        metavar="DIR",
        help="save the rendered HTML, element data and screenshots of every page to DIR",
    )
    add(
        "--screenshot-format",
        choices=SCREENSHOT_FORMATS,
        help="image format of screenshots (default: jpeg)",
    )
    add("--max-pages", type=int, metavar="N", help="check at most N pages (default: 50)")
    add(
        "--per-pattern",
        type=int,
        metavar="N",
        help="check at most N pages per URL pattern such as /products/<id>/ (default: 2)",
    )
    add(
        "--include",
        action="append",
        metavar="GLOB",
        help="only check URLs matching GLOB (path like /shop/* or a full URL; repeatable)",
    )
    add("--exclude-url", action="append", metavar="GLOB", help="do not check URLs matching GLOB")
    add(
        "--no-crawl",
        action="store_const",
        const=True,
        default=None,
        help="check only the given URLs, do not follow links",
    )
    add(
        "--runserver",
        action="store_const",
        const=True,
        default=None,
        help="start the Django project in this folder (manage.py runserver with template "
        "source maps), scan it and stop it; problems point at template lines",
    )
    add(
        "--save-auth",
        type=Path,
        metavar="FILE",
        help="open the given login page in a browser window, let you log in by hand and save "
        "the session (cookies, never a password) to FILE when you close the window",
    )
    add(
        "--auth",
        action="append",
        metavar="FILE",
        help="scan logged in with a session saved by --save-auth; repeat it to scan once per "
        "role (findings say which role saw them)",
    )
    add(
        "--embed-screenshots",
        action="store_const",
        const=True,
        default=None,
        help="with --format html -o FILE.html: one file with the screenshots inside "
        "(without it, -o DIR/ writes a report folder)",
    )
    add(
        "--baseline",
        type=Path,
        metavar="SCAN_JSON",
        help="compare with an earlier scan.json: report only new problems and fail only on them",
    )
    add(
        "--write-baseline",
        type=Path,
        metavar="FILE",
        help="write the scan (scan.json) to FILE, to use with --baseline later",
    )
    add(
        "--max-states",
        type=int,
        metavar="N",
        help="open at most N menus, dialogs, tabs and details per page and check them "
        "(default: 10, 0 to turn off)",
    )
    add(
        "--concurrency",
        type=int,
        metavar="N",
        help="open N pages at the same time, each in its own browser (default: 1)",
    )


def options_from(args: argparse.Namespace, config_values: dict) -> BrowserOptions:
    """``[tool.ramplint.browser]`` overridden by the command line. Raises ValueError."""
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
    for name in ("max_pages", "per_pattern", "concurrency"):
        value = getattr(args, name)
        if value is not None:
            if value < 1:
                raise ValueError(f"--{name.replace('_', '-')} must be above 0")
            setattr(options, name, value)
    if args.max_states is not None:
        if args.max_states < 0:
            raise ValueError("--max-states must not be negative")
        options.max_states = args.max_states
    if args.auth:
        options.auth = [str(path) for path in args.auth]
    if args.include:
        options.include = list(args.include)
    if args.exclude_url:
        options.exclude = [*options.exclude, *args.exclude_url]
    if args.no_crawl:
        options.crawl = False
    return options


def _warn(message: str) -> None:
    print(f"ramplint: warning: {message}", file=sys.stderr)


def filter_start_urls(urls: Sequence[str], options: BrowserOptions) -> list[str]:
    """The given URLs without duplicates, filtered and capped by the options."""
    result: list[str] = []
    for url in dict.fromkeys(urls):
        if options.denied(url):
            _warn(f"not opening {url}: it matches deny")
        elif not options.allowed(url):
            _warn(f"skipped {url}: excluded by the URL filters")
        else:
            result.append(url)
    if len(result) > options.max_pages:
        _warn(f"checking the first {options.max_pages} of {len(result)} URLs (--max-pages)")
        result = result[: options.max_pages]
    return result


# -- Django project --------------------------------------------------------------


def find_project(workspace: Workspace) -> Project | None:
    """The Django project in the current folder, if there is one."""
    try:
        project = workspace.project_for(workspace.cwd)
    except SettingsNotFound:
        return None
    return project if project is not None and project.settings_module else None


def login_path(project: Project | None, urlconf: UrlConf | None) -> str:
    """The path of ``LOGIN_URL`` (a path or a URL name), else Django's default."""
    value = project.settings.get("LOGIN_URL") if project and project.settings else None
    if isinstance(value, str) and value:
        if "/" in value:
            return value
        pattern = urlconf.by_name(value) if urlconf is not None else None
        if pattern is not None and pattern.is_static:
            return pattern.route
    return DEFAULT_LOGIN_PATH


# -- output ----------------------------------------------------------------------


def coverage_summary(coverage: Sequence[Coverage], pages: int) -> str:
    """``crawled 12 pages of 7 URL patterns; 2 need a sample URL, 1 needs login``."""
    statuses = [c.status for c in coverage]
    scanned = statuses.count(Status.SCANNED)
    parts = [f"crawled {pages} page{'s' if pages != 1 else ''} of {scanned} URL pattern"]
    parts[0] += "" if scanned == 1 else "s"
    for status, singular, plural in (
        (Status.NEEDS_SAMPLE, "needs a sample URL", "need a sample URL"),
        (Status.NEEDS_LOGIN, "needs login", "need login"),
        (Status.ERROR, "failed", "failed"),
        (Status.SKIPPED, "was skipped", "were skipped"),
    ):
        count = statuses.count(status)
        if count:
            parts.append(f"{count} {singular if count == 1 else plural}")
    return "; ".join([parts[0], ", ".join(parts[1:])]) if len(parts) > 1 else parts[0]


def print_coverage(coverage: Sequence[Coverage], err: TextIO) -> None:
    width = max((len(c.route) for c in coverage), default=0)
    for item in coverage:
        name = f"  {item.name}" if item.name else ""
        err.write(f"ramplint:   {item.route:<{width}}  {item.summary}{name}\n")


class UsageError(Exception):
    """A problem with the command line or its files; ramplint exits with 2."""


def run_browser(
    args: argparse.Namespace,
    urls: list[str],
    rules: list[Rule],
    config: Config,
    workspace: Workspace,
    write_output: WriteOutput,
    static: list[Violation] | None = None,
) -> int:
    """Scan ``urls``; ``static`` are template-linter findings to merge (``--runserver``)."""
    from ramplint.browser.session import BrowserUnavailable

    try:
        return _run(args, urls, rules, config, workspace, write_output, static)
    except (UsageError, ValueError, BaselineError, BrowserUnavailable) as exc:
        print(f"ramplint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        # Every session is closed by its context manager; no traceback.
        print("ramplint: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED


def _run(
    args: argparse.Namespace,
    urls: list[str],
    rules: list[Rule],
    config: Config,
    workspace: Workspace,
    write_output: WriteOutput,
    static: list[Violation] | None,
) -> int:
    options = options_from(args, config.browser)
    use_django = config.django and not args.no_django
    project = find_project(workspace) if use_django else None
    if args.runserver and static is None:  # not running yet: start it first
        if project is None:
            raise UsageError("--runserver needs a Django project (manage.py) in this folder")
        return _with_dev_server(args, rules, config, workspace, write_output, project)
    if args.save_auth is not None:
        return _save_auth(args.save_auth, urls, options)

    urls = filter_start_urls(urls, options)
    if not urls:
        raise UsageError("no URL left to check")
    logins = _logins(options)
    urlconf = project_urlconf(project) if project is not None else None
    extra = _urlconf_start_urls(args, urlconf, options, urls[0])
    output = ReportOutput.from_args(args)
    baseline = load_baseline(args.baseline) if args.baseline else None
    login = login_path(project, urlconf)

    try:
        result = _crawl(args, rules, options, logins, urls, extra, urlconf, login, output)
        _report_crawl(args, result, options)
        violations = result.violations
        if static is not None:
            violations = merge_static(violations, static)
        fixed: list[dict[str, object]] = []
        if baseline is not None:
            violations, fixed = _compare(args, violations, baseline)
        viewports = [v.name for v in options.viewports]
        if args.write_baseline is not None:
            write_scan_json(args.write_baseline, scan_data(result, violations, urls, viewports))
            print(f"ramplint: scan written to {args.write_baseline}", file=sys.stderr)
        code = output.write(args, result, violations, urls, viewports, fixed, write_output)
    finally:
        output.close()
    if code == EXIT_ERROR:
        return code
    failing = any(v.baseline != EXISTING for v in violations)
    return EXIT_VIOLATIONS if failing and not args.exit_zero else EXIT_OK


def _logins(options: BrowserOptions) -> list[Role]:
    logins = roles(options.auth)
    for role in logins:
        if unprotected_secret(role.path):
            _warn(
                f"{role.path} holds your session cookies and git does not ignore it; "
                "add it to .gitignore"
            )
    return logins


def _urlconf_start_urls(
    args: argparse.Namespace, urlconf: UrlConf | None, options: BrowserOptions, base: str
) -> list[str]:
    """URLs of the URLconf patterns without parameters, and the configured samples."""
    if urlconf is None:
        return []
    urls, unknown = start_urls(urlconf, options.samples, base)
    for name in unknown:
        _warn(f"sample {name!r} matches no URL pattern name")
    if args.verbose:
        print(f"ramplint: URL patterns from {urlconf.module}", file=sys.stderr)
        for problem in urlconf.unresolved:
            print(f"ramplint:   not read: {problem}", file=sys.stderr)
    return urls


def _crawl(
    args: argparse.Namespace,
    rules: list[Rule],
    options: BrowserOptions,
    logins: list[Role],
    urls: list[str],
    extra: list[str],
    urlconf: UrlConf | None,
    login: str,
    output: ReportOutput,
) -> ScanResult:
    """Crawl once, or once per role with ``--auth``."""
    from ramplint.browser.scan import Crawler

    show_progress = args.verbose or sys.stderr.isatty()

    def progress(index: int, total: int, url: str, viewport: str) -> None:
        if show_progress:
            print(f"[{index}/{total}] {url} ({viewport})", file=sys.stderr)

    results: list[tuple[Role | None, ScanResult]] = []
    for role in logins or [None]:
        scan_options = options
        if role is not None:
            scan_options = replace(options, storage_state=str(role.path))
            print(f"ramplint: scanning as {role.name}", file=sys.stderr)
        crawler = Crawler(
            rules,
            scan_options,
            urlconf=urlconf,
            login_path=login,
            progress=progress,
            probes=probes_for(rules, scan_options),
            on_page=output.store.on_page if output.store else None,
        )
        results.append((role, crawler.run(urls, extra)))
    for role, partial in results:
        _hint_expired_login(role, partial, login)
    return combine(results)


def _report_crawl(args: argparse.Namespace, result: ScanResult, options: BrowserOptions) -> None:
    """Pages that could not be checked, and the coverage of the crawl, on stderr."""
    for snapshot in result.snapshots:
        where = f"{snapshot.url} ({snapshot.viewport})"
        if not snapshot.ok:
            _warn(f"cannot open {where}: {snapshot.error}")
        elif not snapshot.is_html:
            _warn(f"skipped {where}: not an HTML page ({snapshot.content_type})")
        elif snapshot.status is not None and snapshot.status >= 400:
            _warn(f"{where} returned HTTP {snapshot.status}")
    if not result.pages_checked:
        raise UsageError("no page could be checked")
    if options.crawl:
        summary = coverage_summary(result.coverage, result.pages_checked)
        print(f"ramplint: {summary}", file=sys.stderr)
        if args.verbose:
            print_coverage(result.coverage, sys.stderr)


def _compare(
    args: argparse.Namespace, violations: list[Violation], baseline: list[dict[str, object]]
) -> tuple[list[Violation], list[dict[str, object]]]:
    comparison = compare(violations, baseline)
    print(
        f"ramplint: compared with {args.baseline}: {len(comparison.new)} new, "
        f"{len(comparison.existing)} existing, {len(comparison.fixed)} fixed",
        file=sys.stderr,
    )
    return comparison.violations, comparison.fixed


def _with_dev_server(
    args: argparse.Namespace,
    rules: list[Rule],
    config: Config,
    workspace: Workspace,
    write_output: WriteOutput,
    project: Project,
) -> int:
    """``--runserver``: lint the templates, start the project, scan it, stop it."""
    from ramplint.django.runserver import DevServer, ServerError

    assert project.settings_module is not None
    files = list(workspace.files([]))
    static = workspace.lint(files, [rule for rule in rules if not rule.browser_only])
    server = DevServer(project.root, project.settings_module)
    print(f"ramplint: starting {project.settings_module} on {server.url}", file=sys.stderr)
    try:
        with server:
            try:
                return run_browser(
                    args, [server.url], rules, config, workspace, write_output, static=static
                )
            finally:
                if args.verbose and server.output.strip():
                    print("ramplint: server output:", file=sys.stderr)
                    print(server.output.rstrip(), file=sys.stderr)
    except ServerError as exc:
        print(f"ramplint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def combine(results: list[tuple[Role | None, ScanResult]]) -> ScanResult:
    """One result from the scans of several roles; findings say which role saw them."""
    if len(results) == 1 and results[0][0] is None:
        return results[0][1]
    combined = ScanResult()
    violations = []
    for role, result in results:
        assert role is not None
        violations.extend(replace(v, role=role.name) for v in result.violations)
        combined.snapshots.extend(result.snapshots)
        combined.coverage.extend(result.coverage)
        combined.endpoints.extend(result.endpoints)
        combined.actions.extend(result.actions)
        combined.fragments.extend(result.fragments)
        combined.manual.extend(result.manual)
    combined.violations = merge_findings(violations)
    return combined


def _hint_expired_login(role: Role | None, result: ScanResult, login: str) -> None:
    needs_login = [c for c in result.coverage if c.status == Status.NEEDS_LOGIN]
    if not needs_login:
        return
    pages = sum(len(c.login_required) for c in needs_login)
    if role is None:
        _warn(
            f"{pages} page(s) redirected to the login page {login}; scan them logged in with "
            f"--save-auth auth.json <login URL>, then --auth auth.json"
        )
    else:
        _warn(
            f"{pages} page(s) still redirected to {login} as {role.name}: the saved login in "
            f"{role.path} may have expired; run --save-auth {role.path} <login URL> again"
        )


def _save_auth(path: Path, urls: list[str], options: BrowserOptions) -> int:
    from ramplint.browser.session import BrowserUnavailable

    if len(urls) != 1:
        print("ramplint: error: --save-auth needs exactly one URL: the login page", file=sys.stderr)
        return EXIT_ERROR
    print(
        f"ramplint: log in in the browser window, then close it to save the session to {path}",
        file=sys.stderr,
    )
    try:
        save_auth(urls[0], path, replace(options, headed=True))
    except BrowserUnavailable as exc:
        print(f"ramplint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"ramplint: saved the session to {path}; scan with --auth {path}", file=sys.stderr)
    if unprotected_secret(path):
        _warn(f"{path} holds your session cookies and git does not ignore it; add it to .gitignore")
    return EXIT_OK


class ReportOutput:
    """Where the report goes: the usual writers, a report folder, or one embedded file."""

    def __init__(
        self,
        folder: Path | None = None,
        single: Path | None = None,
        store: ScreenshotStore | None = None,
        workdir: tempfile.TemporaryDirectory[str] | None = None,
    ) -> None:
        self.folder = folder
        self.single = single
        self.store = store
        self._workdir = workdir

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> ReportOutput:
        html = args.format == "html" and not args.statistics
        if args.embed_screenshots:
            if not html or args.output is None or args.output.suffix.lower() != ".html":
                raise ValueError("--embed-screenshots needs --format html -o FILE.html")
            workdir = tempfile.TemporaryDirectory(prefix="ramplint-shots-")
            return cls(
                single=args.output, store=ScreenshotStore(Path(workdir.name)), workdir=workdir
            )
        if html and args.output is not None and args.output.suffix.lower() != ".html":
            try:  # fail before the crawl, not after it
                (args.output / "screenshots").mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ValueError(f"cannot write the report to {args.output}: {exc}") from None
            return cls(folder=args.output, store=ScreenshotStore(args.output))
        return cls()

    def close(self) -> None:
        """Remove the temporary screenshots of ``--embed-screenshots``."""
        if self._workdir is not None:
            self._workdir.cleanup()
            self._workdir = None

    def write(
        self,
        args: argparse.Namespace,
        result: ScanResult,
        violations: list[Violation],
        urls: Sequence[str],
        viewports: Sequence[str],
        fixed: Sequence[dict[str, object]],
        write_output: WriteOutput,
    ) -> int:
        """Write the report; returns ``EXIT_ERROR`` when it cannot be written."""
        summary = f"{len(violations)} problems on {result.pages_checked} pages"
        try:
            if self.folder is not None and self.store is not None:
                index = write_folder(
                    self.folder, result, violations, self.store, urls, viewports, fixed
                )
                print(f"{summary}. html report written to {index}")
                return EXIT_OK
            if self.single is not None and self.store is not None:
                size = write_single(self.single, result, violations, self.store, viewports, fixed)
                print(f"{summary}. html report written to {self.single}")
                if size > EMBED_WARNING_BYTES:
                    _warn(
                        f"{self.single} is {size // (1024 * 1024)} MB; a report folder "
                        "(-o DIR/) keeps the screenshots as separate files"
                    )
                return EXIT_OK
        except OSError as exc:
            print(f"ramplint: error: cannot write the report: {exc}", file=sys.stderr)
            return EXIT_ERROR
        shown = violations
        if args.baseline is not None and _text_like(args):
            existing = len(violations) - len([v for v in violations if v.baseline != EXISTING])
            shown = [v for v in violations if v.baseline != EXISTING]
            print(
                f"ramplint: {existing} existing and {len(fixed)} fixed problems are not shown "
                f"(baseline {args.baseline})",
                file=sys.stderr,
            )
        with browser_report(viewports, fixed=fixed):
            return write_output(args, shown, result.pages_checked)


def _text_like(args: argparse.Namespace) -> bool:
    return (args.format or "text") in ("text", "github") and not args.statistics
