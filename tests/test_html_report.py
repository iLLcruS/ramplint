from __future__ import annotations

import io
import re

from ramplint import lint_source
from ramplint.linter import Violation
from ramplint.reporters import REPORTERS

VIOLATIONS = [
    Violation("templates/a.html", 3, 1, "RL101", "img-alt", '<img> is missing an alt="" & <b>'),
    Violation("templates/a.html", 9, 5, "RL502", "link-name", "<a> link has no name"),
    Violation("templates/b.html", 1, 1, "RL101", "img-alt", "<img> is missing an alt"),
]


def render(violations, files_checked=4) -> str:
    out = io.StringIO()
    REPORTERS["html"].write(violations, files_checked, out, False)
    return out.getvalue()


def test_is_registered():
    assert "html" in REPORTERS


def test_summary_and_grouping():
    html = render(VIOLATIONS)
    assert "<h1>3 accessibility problems in 2 templates</h1>" in html
    assert "<dt>Templates checked</dt><dd>4</dd>" in html
    assert "<dt>Problems</dt><dd>3</dd>" in html
    assert "<dt>Templates with problems</dt><dd>2</dd>" in html
    # One section per file, in order, linked from the overview.
    assert html.count('<section class="file"') == 2
    assert html.index('id="file-1-title">templates/a.html') < html.index(
        'id="file-2-title">templates/b.html'
    )
    assert 'href="#file-1"' in html and 'href="#file-2"' in html
    # Rules are counted, most frequent first.
    assert html.index("img-alt</span></th>") < html.index("link-name</span></th>")


def test_messages_are_escaped():
    html = render(VIOLATIONS)
    assert "&lt;img&gt; is missing an alt=&quot;&quot; &amp; &lt;b&gt;" in html
    assert "<b>" not in html


def test_self_contained():
    html = render(VIOLATIONS)
    assert "<script" not in html
    assert "<link" not in html
    assert "@import" not in html
    assert not re.search(r'src="https?:', html)
    assert "prefers-color-scheme: dark" in html


def test_report_passes_ramplint():
    assert lint_source(render(VIOLATIONS)) == []
    assert lint_source(render([])) == []


def test_clean_report():
    html = render([], files_checked=1)
    assert "No accessibility problems in 1 template" in html
    assert '<section class="file"' not in html
