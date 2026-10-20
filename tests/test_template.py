from __future__ import annotations

from ramplint import lint_source
from ramplint.template import MARKUP, TEXT, prepare


def test_geometry_is_preserved():
    source = '<p>{{ a }}</p>\n{% if x %}\n<img src="{% static "a.png" %}">{# note #}\n{% endif %}'
    html = prepare(source).html
    assert len(html) == len(source)
    assert html.count("\n") == source.count("\n")
    assert html.index("<img") == source.index("<img")


def test_placeholders():
    html = prepare('{{ x }}|{% trans "a" %}|{% include "b.html" %}|{% if y %}|{# c #}').html
    parts = html.split("|")
    assert parts[0].startswith(TEXT)
    assert parts[1].startswith(TEXT)
    assert parts[2].startswith(MARKUP)
    assert parts[3].strip() == ""
    assert parts[4].strip() == ""


def test_jinja_whitespace_control():
    html = prepare("{%- if x -%}<b>{{- y -}}</b>{%- endif %}").html
    assert html.strip().startswith("<b>")
    assert TEXT in html


def test_comment_block_is_ignored():
    source = """{% comment %}
    <img src="old.png">
    {% endcomment %}"""
    assert lint_source(source) == []


def test_multiline_tag_keeps_line_numbers():
    source = '{% include "x.html" with\n   a=1\n   b=2 %}\n<img src="a.png">'
    [violation] = lint_source(source)
    assert (violation.line, violation.col) == (4, 1)


def test_column_is_accurate_after_tags():
    source = '{% if a %}<span>{{ b }}</span><img src="x.png">{% endif %}'
    [violation] = lint_source(source)
    assert violation.col == source.index("<img") + 1


def test_suppress_same_line():
    source = '<img src="a.png"> {# ramplint: ignore RL101 #}'
    assert lint_source(source) == []


def test_suppress_next_line():
    source = '{# ramplint: ignore img-alt #}\n<img src="a.png">\n<img src="b.png">'
    assert [v.line for v in lint_source(source)] == [3]


def test_suppress_html_comment_all_rules():
    source = '<!-- ramplint: ignore -->\n<a href="/"><img src="a.png"></a>'
    assert lint_source(source) == []


def test_suppress_other_rule_only():
    source = '{# ramplint: ignore RL502 #}\n<img src="a.png">'
    assert [v.code for v in lint_source(source)] == ["RL101"]


def test_ignore_file():
    source = '{# ramplint: ignore-file RL101 #}\n<img src="a.png">\n<a href="/"></a>'
    assert [v.code for v in lint_source(source)] == ["RL502"]


def test_ignore_file_everything():
    source = '{# ramplint: ignore-file #}\n<img src="a.png">\n<a href="/"></a>'
    assert lint_source(source) == []


def test_unbalanced_fragment_does_not_crash():
    source = "</div></div>{% block x %}<td><img src=a></tr></table>{% endblock %}<p><p>"
    assert [v.code for v in lint_source(source)] == ["RL101"]


def test_script_content_is_ignored():
    source = '<script>const html = "<img src=x>";</script>'
    assert lint_source(source) == []
