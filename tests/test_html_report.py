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
    assert html.index('#rl101-img-alt">img-alt</a>') < html.index('#rl502-link-name">link-name</a>')


def test_messages_are_escaped():
    html = render(VIOLATIONS)
    assert "&lt;img&gt; is missing an alt=&quot;&quot; &amp; &lt;b&gt;" in html
    assert "<b>" not in html


def test_self_contained():
    html = render(VIOLATIONS)
    assert "<script src" not in html
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


# --------------------------------------------------------------------------
# Snippets, rule links and filters (#10)
# --------------------------------------------------------------------------


def test_snippet_shows_context_and_highlights_line(tmp_path):
    template = tmp_path / "page.html"
    template.write_text("\n".join(f"<p>line {n}</p>" for n in range(1, 11)) + "\n")
    html = render([Violation(str(template), 5, 1, "RL101", "img-alt", "msg")])
    snippet = html[html.index('<pre class="snippet"') : html.index("</pre>")]
    for number in (3, 4, 5, 6, 7):
        assert f'<span class="ln">{number}</span>' in snippet
    assert '<span class="ln">2</span>' not in snippet
    assert '<span class="ln">8</span>' not in snippet
    assert '<span class="src-line hl"><span class="ln">5</span>&lt;p&gt;line 5' in snippet
    assert snippet.count(" hl") == 1


def test_snippet_at_file_edges(tmp_path):
    template = tmp_path / "short.html"
    template.write_text("<a>\n<b>\n")
    html = render([Violation(str(template), 1, 1, "RL101", "img-alt", "msg")])
    assert '<span class="ln">1</span>' in html and '<span class="ln">2</span>' in html
    assert '<span class="ln">3</span>' not in html


def test_missing_file_has_no_snippet():
    html = render([Violation("does/not/exist.html", 1, 1, "RL101", "img-alt", "msg")])
    assert '<pre class="snippet"' not in html


def test_long_lines_are_truncated(tmp_path):
    template = tmp_path / "long.html"
    template.write_text("x" * 5000 + "\n")
    html = render([Violation(str(template), 1, 1, "RL101", "img-alt", "msg")])
    assert "x" * 5000 not in html
    assert "…" in html


def test_rules_link_to_documentation():
    html = render(VIOLATIONS)
    assert 'href="https://github.com/iLLcruS/ramplint#rl101-img-alt"' in html
    assert 'href="https://github.com/iLLcruS/ramplint#rl502-link-name"' in html


def test_filters_are_progressive_enhancement():
    html = render(VIOLATIONS)
    # Hidden without JavaScript, revealed by the inline script.
    assert '<form class="filters box" id="filters" hidden>' in html
    assert '<option value="RL101">RL101 img-alt</option>' in html
    assert '<option value="file-2">templates/b.html</option>' in html
    assert html.count('<tr data-rule="RL101">') == 2
    assert "<script>" in html and "<script src" not in html
    assert 'data-total="3"' in html


def test_report_with_snippets_passes_ramplint(tmp_path):
    template = tmp_path / "bad.html"
    template.write_text('<img src="a.png">\n<a href="/"></a>\n<input name="q">\n')
    violations = lint_source(template.read_text(), path=str(template))
    html = render(violations)
    assert '<pre class="snippet"' in html
    assert lint_source(html) == []
