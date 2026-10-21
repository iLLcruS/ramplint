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


def _rule_table(violations: Sequence[Violation]) -> str:
    counts = Counter((v.code, v.name) for v in violations)
    rows = []
    for (code, name), count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        rule = REGISTRY.get(code)
        summary = escape(rule.summary) if rule else ""
        rows.append(
            "<tr>"
            f'<th scope="row"><span class="code">{escape(code)}</span>'
            f'<span class="rule-name">{escape(name)}</span></th>'
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
    for index, (path, group) in enumerate(groupby(violations, key=lambda v: v.path), start=1):
        items = list(group)
        anchor = f"file-{index}"
        count = _plural(len(items), "problem")
        links.append(
            f'<li><a href="#{anchor}">{escape(path)}</a><span class="count">{count}</span></li>'
        )
        rows = "".join(
            "<tr>"
            f'<td class="loc">{v.line}:{v.col}</td>'
            f'<th scope="row"><span class="code">{escape(v.code)}</span>'
            f'<span class="rule-name">{escape(v.name)}</span></th>'
            f'<td class="message">{escape(v.message)}</td>'
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
        "</body>\n</html>\n"
    )
