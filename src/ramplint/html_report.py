"""Self-contained HTML report (``--format html``).

One file, no external CSS, JS or fonts, so it works offline and as an email
attachment. Light and dark themes follow the operating system setting.
The page is built to pass ramplint itself.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from html import escape
from importlib.resources import files
from itertools import groupby
from pathlib import Path
from typing import TextIO
from urllib.parse import urlsplit

from ramplint import __version__
from ramplint.browser.urls import url_pattern
from ramplint.linter import Violation
from ramplint.reporters import affected_count, report_context, reporter
from ramplint.rules import REGISTRY

_CSS = files("ramplint").joinpath("report.css").read_text(encoding="utf-8")


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _headline(violations: Sequence[Violation], files_checked: int) -> str:
    noun = report_context().noun
    if not violations:
        return f"No accessibility problems in {_plural(files_checked, noun)}"
    affected = affected_count(violations)
    return f"{_plural(len(violations), 'accessibility problem')} in {_plural(affected, noun)}"


_CONTEXT_LINES = 2
_MAX_LINE_LENGTH = 200

_SCRIPT = files("ramplint").joinpath("report.js").read_text(encoding="utf-8")


class _SourceCache:
    """Reads each template once; missing or unreadable files have no snippet."""

    def __init__(self) -> None:
        self._lines: dict[str, list[str] | None] = {}

    def lines(self, path: str) -> list[str] | None:
        if path not in self._lines:
            try:
                text = Path(path).read_text(encoding="utf-8", errors="replace")
                self._lines[path] = text.splitlines()
            except OSError:
                self._lines[path] = None
        return self._lines[path]


def folder_nav(nav: Sequence[tuple[str, str]], current: str) -> str:
    """Links between the pages of a browser report folder."""
    if not nav:
        return ""
    items = "".join(
        f'<li><a href="{escape(href)}" aria-current="page">{escape(label)}</a></li>'
        if label == current
        else f'<li><a href="{escape(href)}">{escape(label)}</a></li>'
        for label, href in nav
    )
    return f'<nav class="folder-nav" aria-label="Report"><ul>{items}</ul></nav>'


def _snippet(lines: list[str] | None, line: int) -> str:
    """Template source around ``line`` with that line highlighted."""
    if not lines or not 1 <= line <= len(lines):
        return ""
    first = max(1, line - _CONTEXT_LINES)
    last = min(len(lines), line + _CONTEXT_LINES)
    rendered = []
    for number in range(first, last + 1):
        text = lines[number - 1].expandtabs(4).rstrip()
        if len(text) > _MAX_LINE_LENGTH:
            text = text[:_MAX_LINE_LENGTH] + "…"
        css = "src-line hl" if number == line else "src-line"
        rendered.append(
            f'<span class="{css}"><span class="ln">{number}</span>{escape(text)}</span>'
        )
    return (
        f'<pre class="snippet" tabindex="0" aria-label="Template source around line {line}">'
        f"<code>{''.join(rendered)}</code></pre>"
    )


def _rule_link(code: str, name: str) -> str:
    rule = REGISTRY.get(code)
    label = escape(name)
    if rule is None:
        return f'<span class="rule-name">{label}</span>'
    return f'<a class="rule-name" href="{escape(rule.docs_url)}">{label}</a>'


def _location_cell(v: Violation) -> str:
    location = v.template_location
    if location is not None:
        return f"{location[1]}:{location[2]}"
    if v.in_browser:
        return escape((v.viewport or "").replace(",", ", "))
    return f"{v.line}:{v.col}"


def _source_line(v: Violation) -> int:
    location = v.template_location
    return location[1] if location is not None else v.line


def _page_link(url: str) -> str:
    """A page of the scan: to its page report when there is one."""
    href = report_context().page_links.get(url, url)
    return f'<a href="{escape(href)}">{escape(url)}</a>'


def _element(v: Violation) -> str:
    """Where a browser finding is: page, element, state, role, and a picture of it."""
    if not v.in_browser:
        return ""
    parts = [f'<p class="pages">On {_page_link(v.path)}</p>']
    if v.selector:
        parts.append(f'<code class="selector">{escape(v.selector)}</code>')
    notes = []
    if v.state:
        notes.append(escape(v.state))
    if v.role:
        notes.append(f"seen as {escape(v.role.replace(',', ', '))}")
    if v.confirmed:
        notes.append("also found in the template, confirmed in the browser")
    if notes:
        parts.append(f'<p class="pages">{"; ".join(notes)}</p>')
    others = v.locations[1:]
    if others:
        links = ", ".join(_page_link(url) for url in others)
        parts.append(f'<p class="pages">Also on: {links}</p>')
    if v.screenshot:
        parts.append(f'<img class="crop" src="{escape(v.screenshot)}" alt="" loading="lazy">')
    return "".join(parts)


def _row_attributes(v: Violation) -> str:
    """``data-*`` attributes the filters use."""
    attributes = f' data-rule="{escape(v.code)}"'
    if v.baseline:
        attributes += f' data-baseline="{escape(v.baseline)}"'
    return attributes


def _baseline_badge(v: Violation) -> str:
    return '<span class="new">New</span>' if v.baseline == "new" else ""


def _groups_title(violations: Sequence[Violation]) -> str:
    """The list of sections: templates, URL patterns (browser) or files."""
    if any(v.template for v in violations):
        return "Templates with problems"
    if any(v.in_browser for v in violations):
        return "URL patterns with problems"
    return f"{report_context().noun.capitalize()}s with problems"


def _baseline_figures(violations: Sequence[Violation]) -> str:
    if not any(v.baseline for v in violations) and not report_context().fixed:
        return ""
    new = sum(1 for v in violations if v.baseline == "new")
    fixed = len(report_context().fixed)
    return f"<div><dt>New</dt><dd>{new}</dd></div><div><dt>Fixed</dt><dd>{fixed}</dd></div>"


def _fixed_section() -> str:
    """``--baseline``: what was in the baseline and is gone now."""
    fixed = report_context().fixed
    if not fixed:
        return ""
    items = "".join(
        f'<li><span class="code">{escape(str(entry.get("code", "")))}</span> '
        f"{escape(str(entry.get('message', '')))} "
        f'<span class="pages">{escape(str(entry.get("template") or entry.get("path", "")))}'
        "</span></li>"
        for entry in fixed
    )
    return (
        '<section class="box fixed" aria-labelledby="fixed-title">'
        f'<h2 id="fixed-title">Fixed since the baseline ({len(fixed)})</h2>'
        f'<ul class="page-problems">{items}</ul></section>'
    )


def _group(v: Violation) -> str:
    """Findings are listed by template, else by URL pattern (browser), else by file."""
    location = v.template_location
    if location is not None:
        return location[0]
    if v.in_browser:
        return urlsplit(url_pattern(v.url or v.path)).path or "/"
    return v.path


def _filters(violations: Sequence[Violation]) -> str:
    """Filter controls. Hidden until the script runs, so the page still works
    in email clients and viewers that block JavaScript."""
    rule_options = "".join(
        f'<option value="{escape(code)}">{escape(code)} {escape(name)}</option>'
        for code, name in sorted({(v.code, v.name) for v in violations})
    )
    paths = list(dict.fromkeys(_group(v) for v in violations))
    file_options = "".join(
        f'<option value="file-{index}">{escape(path)}</option>'
        for index, path in enumerate(paths, start=1)
    )
    noun = report_context().noun
    baseline = ""
    if any(v.baseline for v in violations):
        baseline = (
            '<label for="filter-baseline">Status</label>'
            '<select id="filter-baseline"><option value="">New and existing</option>'
            '<option value="new">New</option><option value="existing">Existing</option>'
            "</select>"
        )
    return (
        '<form class="filters box" id="filters" hidden>'
        '<h2 id="filters-title">Filter problems</h2>'
        '<div class="filter-row">'
        '<label for="filter-rule">Rule</label>'
        f'<select id="filter-rule"><option value="">All rules</option>{rule_options}</select>'
        f'<label for="filter-file">{noun.capitalize()}</label>'
        f'<select id="filter-file"><option value="">All {noun}s</option>{file_options}</select>'
        f"{baseline}"
        '<button type="reset">Show all</button>'
        "</div>"
        f'<p id="filter-status" class="filter-status" aria-live="polite" '
        f'data-total="{len(violations)}"></p>'
        "</form>"
    )


def _rule_table(violations: Sequence[Violation]) -> str:
    counts = Counter((v.code, v.name) for v in violations)
    rows = []
    for (code, name), count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        rule = REGISTRY.get(code)
        summary = escape(rule.summary) if rule else ""
        rows.append(
            "<tr>"
            f'<th scope="row"><span class="code">{escape(code)}</span>'
            f"{_rule_link(code, name)}</th>"
            f'<td class="what">{summary}</td>'
            f'<td class="num">{count}</td>'
            "</tr>"
        )
    return (
        "<table>"
        "<caption>Most frequent first</caption>"
        '<thead><tr><th scope="col">Rule</th><th scope="col" class="what">What it checks</th>'
        '<th scope="col" class="num">Problems</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _file_sections(violations: Sequence[Violation]) -> tuple[str, str]:
    """Return (list of links to files, one section per file)."""
    links: list[str] = []
    sections: list[str] = []
    sources = _SourceCache()
    order = {key: index for index, key in enumerate(dict.fromkeys(map(_group, violations)))}
    ordered = sorted(violations, key=lambda v: order[_group(v)])
    for index, (path, group) in enumerate(groupby(ordered, key=_group), start=1):
        items = list(group)
        anchor = f"file-{index}"
        count = _plural(len(items), "problem")
        links.append(
            f'<li><a href="#{anchor}">{escape(path)}</a><span class="count">{count}</span></li>'
        )
        on_template = items[0].template_location is not None or not items[0].in_browser
        lines = sources.lines(path) if on_template else None
        rows = "".join(
            f"<tr{_row_attributes(v)}>"
            f'<td class="loc">{_location_cell(v)}</td>'
            f'<th scope="row"><span class="code">{escape(v.code)}</span>'
            f"{_rule_link(v.code, v.name)}{_baseline_badge(v)}</th>"
            f'<td class="message">{escape(v.message)}{_element(v)}'
            f"{_snippet(lines, _source_line(v))}</td>"
            "</tr>"
            for v in items
        )
        loc_header = "Line" if on_template else "Viewport"
        sections.append(
            f'<section class="file" id="{anchor}" aria-labelledby="{anchor}-title">'
            f'<h2 id="{anchor}-title">{escape(path)}<span class="count">{count}</span></h2>'
            '<div class="box"><table class="problems">'
            '<colgroup><col class="col-loc"><col class="col-rule"><col></colgroup>'
            f'<thead><tr><th scope="col">{loc_header}</th><th scope="col">Rule</th>'
            '<th scope="col">Problem</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div></section>"
        )
    return "".join(links), "".join(sections)


@reporter("html", "Self-contained HTML page to share or attach to an email")
def report_html(
    violations: Sequence[Violation], files_checked: int, out: TextIO, color: bool = False
) -> None:
    headline = _headline(violations, files_checked)
    noun = report_context().noun
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    affected = affected_count(violations)

    if violations:
        file_links, file_sections = _file_sections(violations)
        body = (
            '<div class="overview">'
            '<section class="box" aria-labelledby="by-rule"><h2 id="by-rule">Problems by rule</h2>'
            f"{_rule_table(violations)}</section>"
            '<nav class="box" aria-labelledby="by-file">'
            f'<h2 id="by-file">{_groups_title(violations)}</h2>'
            f'<ul class="files">{file_links}</ul></nav>'
            "</div>"
            f"{_filters(violations)}"
            f"{file_sections}"
        )
    else:
        body = (
            f'<p class="clean">Every checked {noun} passed all '
            f"{_plural(len(REGISTRY), 'rule')}.</p>"
        )

    out.write(
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="generator" content="ramplint">\n'
        f"<title>{escape(headline)} - ramplint report</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n<body>\n"
        '<header class="sign"><div class="wrap">'
        f"{folder_nav(report_context().nav, 'Problems')}"
        f"<h1>{escape(headline)}</h1>"
        f'<p class="meta">ramplint {escape(__version__)} accessibility report, '
        f"generated {generated}</p>"
        '<dl class="figures">'
        f"<div><dt>{noun.capitalize()}s checked</dt><dd>{files_checked}</dd></div>"
        f"<div><dt>Problems</dt><dd>{len(violations)}</dd></div>"
        f"<div><dt>{noun.capitalize()}s with problems</dt><dd>{affected}</dd></div>"
        f"{_baseline_figures(violations)}"
        "</dl></div></header>\n"
        f'<main class="wrap">{body}{_fixed_section()}</main>\n'
        '<footer class="wrap">Generated by '
        '<a href="https://github.com/iLLcruS/ramplint">ramplint</a>. '
        "Static checks catch structural problems; also test with a keyboard and a "
        "screen reader.</footer>\n"
        f"<script>{_SCRIPT}</script>\n"
        "</body>\n</html>\n"
    )
