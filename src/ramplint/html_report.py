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

from ramplint import __version__
from ramplint.linter import Violation
from ramplint.reporters import reporter
from ramplint.rules import REGISTRY

_CSS = files("ramplint").joinpath("report.css").read_text(encoding="utf-8")


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _headline(violations: Sequence[Violation], files_checked: int) -> str:
    if not violations:
        return f"No accessibility problems in {_plural(files_checked, 'template')}"
    affected = len({v.path for v in violations})
    return f"{_plural(len(violations), 'accessibility problem')} in {_plural(affected, 'template')}"


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


def _filters(violations: Sequence[Violation]) -> str:
    """Filter controls. Hidden until the script runs, so the page still works
    in email clients and viewers that block JavaScript."""
    rule_options = "".join(
        f'<option value="{escape(code)}">{escape(code)} {escape(name)}</option>'
        for code, name in sorted({(v.code, v.name) for v in violations})
    )
    paths = list(dict.fromkeys(v.path for v in violations))
    file_options = "".join(
        f'<option value="file-{index}">{escape(path)}</option>'
        for index, path in enumerate(paths, start=1)
    )
    return (
        '<form class="filters box" id="filters" hidden>'
        '<h2 id="filters-title">Filter problems</h2>'
        '<div class="filter-row">'
        '<label for="filter-rule">Rule</label>'
        f'<select id="filter-rule"><option value="">All rules</option>{rule_options}</select>'
        '<label for="filter-file">Template</label>'
        f'<select id="filter-file"><option value="">All templates</option>{file_options}</select>'
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
    for index, (path, group) in enumerate(groupby(violations, key=lambda v: v.path), start=1):
        items = list(group)
        anchor = f"file-{index}"
        count = _plural(len(items), "problem")
        links.append(
            f'<li><a href="#{anchor}">{escape(path)}</a><span class="count">{count}</span></li>'
        )
        lines = sources.lines(path)
        rows = "".join(
            f'<tr data-rule="{escape(v.code)}">'
            f'<td class="loc">{v.line}:{v.col}</td>'
            f'<th scope="row"><span class="code">{escape(v.code)}</span>'
            f"{_rule_link(v.code, v.name)}</th>"
            f'<td class="message">{escape(v.message)}{_snippet(lines, v.line)}</td>'
            "</tr>"
            for v in items
        )
        sections.append(
            f'<section class="file" id="{anchor}" aria-labelledby="{anchor}-title">'
            f'<h2 id="{anchor}-title">{escape(path)}<span class="count">{count}</span></h2>'
            '<div class="box"><table class="problems">'
            '<colgroup><col class="col-loc"><col class="col-rule"><col></colgroup>'
            '<thead><tr><th scope="col">Line</th><th scope="col">Rule</th>'
            '<th scope="col">Problem</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div></section>"
        )
    return "".join(links), "".join(sections)


@reporter("html", "Self-contained HTML page to share or attach to an email")
def report_html(
    violations: Sequence[Violation], files_checked: int, out: TextIO, color: bool = False
) -> None:
    headline = _headline(violations, files_checked)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    affected = len({v.path for v in violations})

    if violations:
        file_links, file_sections = _file_sections(violations)
        body = (
            '<div class="overview">'
            '<section class="box" aria-labelledby="by-rule"><h2 id="by-rule">Problems by rule</h2>'
            f"{_rule_table(violations)}</section>"
            '<nav class="box" aria-labelledby="by-file">'
            '<h2 id="by-file">Templates with problems</h2>'
            f'<ul class="files">{file_links}</ul></nav>'
            "</div>"
            f"{_filters(violations)}"
            f"{file_sections}"
        )
    else:
        body = (
            '<p class="clean">Every checked template passed all '
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
        f"<h1>{escape(headline)}</h1>"
        f'<p class="meta">ramplint {escape(__version__)} accessibility report, '
        f"generated {generated}</p>"
        '<dl class="figures">'
        f"<div><dt>Templates checked</dt><dd>{files_checked}</dd></div>"
        f"<div><dt>Problems</dt><dd>{len(violations)}</dd></div>"
        f"<div><dt>Templates with problems</dt><dd>{affected}</dd></div>"
        "</dl></div></header>\n"
        f'<main class="wrap">{body}</main>\n'
        '<footer class="wrap">Generated by '
        '<a href="https://github.com/iLLcruS/ramplint">ramplint</a>. '
        "Static checks catch structural problems; also test with a keyboard and a "
        "screen reader.</footer>\n"
        f"<script>{_SCRIPT}</script>\n"
        "</body>\n</html>\n"
    )
