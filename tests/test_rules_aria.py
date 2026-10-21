from __future__ import annotations

import pytest

from ramplint import lint_source, select_rules


def messages(source: str, code: str) -> list[str]:
    return [v.message for v in lint_source(source, rules=select_rules([code]))]


# --------------------------------------------------------------------------
# RL701 aria-role
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<div role="dailog">',
        '<div role="buton">',
        '<div role="foo bar">',
        '<div role="widget">',
        '<div role="landmark">',
        '<div role="Widget">',
    ],
)
def test_aria_role_violations(lint, source):
    assert lint(source, "RL701") == [("RL701", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<div role="dialog">',
        '<nav role="navigation">',
        '<div role="BUTTON">',
        '<div role="switch checkbox">',
        '<div role="foo button">',
        '<svg role="graphics-document"></svg>',
        '<section role="doc-chapter">',
        '<div role="{{ widget_role }}">',
        '<div role="">',
        "<div {{ attrs }}>",
    ],
)
def test_aria_role_ok(lint, source):
    assert lint(source, "RL701") == []


def test_aria_role_suggestion():
    assert 'did you mean "dialog"?' in messages('<div role="dailog">', "RL701")[0]


# --------------------------------------------------------------------------
# RL702 aria-valid-attr
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    ['<button aria-lable="x">x</button>', '<div aria-labeledby="t">', '<div aria-hiden="true">'],
)
def test_aria_valid_attr_violations(lint, source):
    assert lint(source, "RL702") == [("RL702", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<button aria-label="Close">x</button>',
        '<div aria-description="More">',
        '<div ARIA-HIDDEN="true">',
        '<div aria-{{ name }}="x">',
        "<div {{ aria_attrs }}>",
        '<div data-aria-thing="x">',
    ],
)
def test_aria_valid_attr_ok(lint, source):
    assert lint(source, "RL702") == []


def test_aria_valid_attr_suggestion():
    message = messages('<div aria-labeledby="t">', "RL702")[0]
    assert 'did you mean "aria-labelledby"?' in message


# --------------------------------------------------------------------------
# RL703 aria-valid-attr-value
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<div aria-hidden="yes">',
        '<div aria-disabled="1">',
        '<div aria-busy="">',
        '<div role="checkbox" aria-checked="checked">',
        '<div aria-live="loud">',
        '<a href="/" aria-current="active">x</a>',
        '<div aria-relevant="additions everything">',
        '<div role="heading" aria-level="0">',
        '<div role="heading" aria-level="two">',
        '<div role="slider" aria-valuenow="high">',
        '<div aria-labelledby="">',
        '<div aria-controls="  ">',
        '<div role="dialog" aria-labelledby="title"></div>',
        '<p id="a">x</p><div aria-describedby="a b"></div>',
    ],
)
def test_aria_value_violations(lint, source):
    assert [code for code, _ in lint(source, "RL703")] == ["RL703"]


@pytest.mark.parametrize(
    "source",
    [
        '<div aria-hidden="true">',
        '<div aria-hidden="TRUE">',
        '<div aria-expanded="undefined">',
        '<div role="checkbox" aria-checked="mixed">',
        '<div aria-live="polite">',
        '<a href="/" aria-current="page">x</a>',
        '<div aria-relevant="additions text">',
        '<div role="heading" aria-level="3">',
        '<div role="slider" aria-valuenow="-1.5" aria-valuemin="-10" aria-valuemax="1e2">',
        '<div aria-setsize="-1">',
        '<div aria-hidden="{{ hidden }}">',
        '<div aria-checked="{% if on %}true{% else %}false{% endif %}">',
        '<h2 id="title">T</h2><div role="dialog" aria-labelledby="title"></div>',
        '<div aria-labelledby="t"></div><p id="t">T</p>',
        # The target may be rendered elsewhere: do not check missing ids.
        '{% include "title.html" %}<div aria-labelledby="title"></div>',
        '<div aria-labelledby="title"></div><h2 id="{{ title_id }}">T</h2>',
        '<div aria-labelledby="{{ title_id }}"></div>',
        # aria-controls often points at elements created by JavaScript.
        '<button aria-controls="menu">Menu</button>',
    ],
)
def test_aria_value_ok(lint, source):
    assert lint(source, "RL703") == []


# --------------------------------------------------------------------------
# RL704 aria-required-attr
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<div role="checkbox">',
        '<div role="switch" tabindex="0">',
        '<div role="radio">',
        '<li role="menuitemcheckbox">',
        '<input role="combobox">',
        '<div role="heading">',
        '<div role="slider">',
        '<div role="scrollbar" aria-valuenow="0">',
        '<div role="foo switch">',
    ],
)
def test_aria_required_violations(lint, source):
    assert lint(source, "RL704") == [("RL704", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<div role="checkbox" aria-checked="false">',
        '<div role="switch" aria-checked="{{ on }}">',
        '<div role="combobox" aria-expanded="false">',
        '<div role="heading" aria-level="2">',
        '<div role="scrollbar" aria-controls="list" aria-valuenow="0">',
        '<input type="checkbox" role="switch">',
        '<input type="radio" role="radio">',
        '<input type="range" role="slider">',
        '<h2 role="heading">x</h2>',
        '<select role="combobox"></select>',
        '<div role="{{ role }}">',
        '<div role="switch" {{ attrs }}>',
        '<div role="button">',
    ],
)
def test_aria_required_ok(lint, source):
    assert lint(source, "RL704") == []


# --------------------------------------------------------------------------
# RL705 aria-hidden-focus
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<div aria-hidden="true"><a href="/">x</a></div>',
        '<div aria-hidden="true"><button>x</button></div>',
        '<div aria-hidden="true"><input name="q"></div>',
        '<div aria-hidden="true"><select></select></div>',
        '<div aria-hidden="true"><span tabindex="0">x</span></div>',
        '<div aria-hidden="true"><div contenteditable>x</div></div>',
        '<button aria-hidden="true">x</button>',
        '<div aria-hidden="true"><div aria-hidden="true"><a href="/">x</a></div></div>',
    ],
)
def test_aria_hidden_focus_violations(lint, source):
    assert [code for code, _ in lint(source, "RL705")] == ["RL705"]


@pytest.mark.parametrize(
    "source",
    [
        '<div aria-hidden="true"><a href="/" tabindex="-1">x</a></div>',
        '<div aria-hidden="true"><button disabled>x</button></div>',
        '<div aria-hidden="true"><input type="hidden" name="x"></div>',
        '<div aria-hidden="true"><a name="anchor"></a><span>text</span></div>',
        '<div aria-hidden="true"><div contenteditable="false">x</div></div>',
        '<div aria-hidden="true"><a href="/" tabindex="{{ t }}">x</a></div>',
        '<div aria-hidden="true"><a href="/" {{ attrs }}>x</a></div>',
        '<div aria-hidden="{{ hidden }}"><a href="/">x</a></div>',
        '<div aria-hidden="false"><a href="/">x</a></div>',
        '<template><div aria-hidden="true"><a href="/">x</a></div></template>',
        '<div aria-hidden="true"><template><a href="/">x</a></template></div>',
    ],
)
def test_aria_hidden_focus_ok(lint, source):
    assert lint(source, "RL705") == []


def test_aria_hidden_focus_points_to_hidden_container():
    source = '<div aria-hidden="true">\n  <a href="/">x</a>\n</div>'
    [violation] = lint_source(source, rules=select_rules(["RL705"]))
    assert violation.line == 2
    assert "(line 1)" in violation.message
