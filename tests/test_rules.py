from __future__ import annotations

import pytest

# --------------------------------------------------------------------------
# RL101 img-alt
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<img src="a.png">',
        '<input type="image" src="go.png">',
        '<input type="IMAGE" src="go.png" alt="">',
        '<map><area href="/x" shape="rect" coords="0,0,1,1"></map>',
    ],
)
def test_img_alt_violations(lint, source):
    assert lint(source, "RL101") == [("RL101", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<img src="a.png" alt="Logo">',
        '<img src="a.png" alt="">',
        '<img src="a.png" alt>',
        '<img src="a.png" alt="{{ product.name }}">',
        '<img src="a.png" aria-label="Logo">',
        '<img src="a.png" {{ attrs }}>',
        '<img src="a.png" {% include "alt.html" %}>',
        '<input type="image" src="go.png" alt="Search">',
        '<area shape="rect" coords="0,0,1,1">',
    ],
)
def test_img_alt_ok(lint, source):
    assert lint(source, "RL101") == []


# --------------------------------------------------------------------------
# RL102 iframe-title
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<iframe src="https://example.com/map"></iframe>',
        '<iframe src="/video" title=""></iframe>',
        '<iframe src="/video" title="   "></iframe>',
        '<iframe src="/video" aria-hidden="false"></iframe>',
        '<iframe src="{{ video.url }}"></iframe>',
        '<frameset><frame src="nav.html"></frameset>',
    ],
)
def test_iframe_title_violations(lint, source):
    assert lint(source, "RL102") == [("RL102", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<iframe src="/map" title="Store location map"></iframe>',
        '<iframe src="/video" title="{{ video.title }}"></iframe>',
        '<iframe src="/video" title="{% trans \'Product video\' %}"></iframe>',
        '<iframe src="/video" aria-label="Product video"></iframe>',
        '<iframe src="/video" aria-labelledby="video-heading"></iframe>',
        '<iframe src="/video" {{ attrs }}></iframe>',
        '<iframe src="/pixel" aria-hidden="true"></iframe>',
        '<iframe src="/pixel" aria-hidden="TRUE"></iframe>',
    ],
)
def test_iframe_title_ok(lint, source):
    assert lint(source, "RL102") == []


def test_iframe_title_position(lint):
    source = """
    <div>
      <iframe src="/a" title="A"></iframe>
      <iframe src="/b"></iframe>
    </div>
    """
    assert lint(source, "RL102") == [("RL102", 4)]


# --------------------------------------------------------------------------
# RL201 table-header
# --------------------------------------------------------------------------


def test_table_without_th(lint):
    source = """
    <table>
      <tr><td>Name</td><td>Price</td></tr>
      {% for p in products %}<tr><td>{{ p.name }}</td><td>{{ p.price }}</td></tr>{% endfor %}
    </table>
    """
    assert lint(source, "RL201") == [("RL201", 2)]


@pytest.mark.parametrize(
    "source",
    [
        "<table><tr><th>Name</th></tr><tr><td>x</td></tr></table>",
        '<table><thead><tr><th scope="col">Name</th></tr></thead></table>',
        '<table role="presentation"><tr><td>layout</td></tr></table>',
        '<table role="none"><tr><td>layout</td></tr></table>',
        '<table>{% include "orders/rows.html" %}</table>',
        "<table>{% block rows %}{% endblock %}</table>",
        "<table>{{ form.as_table }}</table>",
        "<table><tbody>{{ rows|safe }}</tbody></table>",
    ],
)
def test_table_ok(lint, source):
    assert lint(source, "RL201") == []


def test_nested_table_th_does_not_count_for_outer(lint):
    source = "<table><tr><td><table><tr><th>x</th></tr></table></td></tr></table>"
    assert lint(source, "RL201") == [("RL201", 1)]


def test_aria_columnheader_is_not_enough(lint):
    source = '<table><tr><td role="columnheader">Name</td></tr></table>'
    assert lint(source, "RL201") == [("RL201", 1)]


def test_variable_inside_cell_does_not_hide_problem(lint):
    assert lint("<table><tr><td>{{ value }}</td></tr></table>", "RL201") == [("RL201", 1)]


# --------------------------------------------------------------------------
# RL301 heading-order / RL302 empty-heading
# --------------------------------------------------------------------------


def test_heading_skip(lint):
    source = """
    <h1>Title</h1>
    <h2>Section</h2>
    <h4>Oops</h4>
    """
    assert lint(source, "RL301") == [("RL301", 4)]


@pytest.mark.parametrize(
    "source",
    [
        "<h1>a</h1><h2>b</h2><h3>c</h3><h2>d</h2><h3>e</h3>",
        "<h1>a</h1><h2>b</h2><h3>c</h3><h1>d</h1>",
        # Fragment that starts below h1 - the parent template owns the h1.
        "{% block content %}<h2>a</h2><h3>b</h3>{% endblock %}",
        "<h3>first heading sets the baseline</h3>",
    ],
)
def test_heading_order_ok(lint, source):
    assert lint(source, "RL301") == []


@pytest.mark.parametrize(
    "source",
    [
        "<h2></h2>",
        "<h2>   </h2>",
        "<h2>{% if x %}{% endif %}</h2>",
        '<h2><i class="icon"></i></h2>',
    ],
)
def test_empty_heading(lint, source):
    assert lint(source, "RL302") == [("RL302", 1)]


@pytest.mark.parametrize(
    "source",
    [
        "<h2>{{ title }}</h2>",
        '<h2>{% trans "Orders" %}</h2>',
        "<h1>{% block title %}{% endblock %}</h1>",
        '<h2><img src="logo.png" alt="ACME"></h2>',
        '<h2 aria-label="Orders"></h2>',
        '<h2 aria-hidden="true"></h2>',
    ],
)
def test_heading_with_content(lint, source):
    assert lint(source, "RL302") == []


# --------------------------------------------------------------------------
# RL303 duplicate-id
# --------------------------------------------------------------------------


def test_duplicate_id_reported_on_second_occurrence(lint):
    source = """
    <label for="email">Email</label>
    <input id="email" type="email">
    <p id="email">We never share your email.</p>
    """
    assert lint(source, "RL303") == [("RL303", 4)]


def test_duplicate_id_message_points_to_first(lint):
    from ramplint import lint_source, select_rules

    [violation] = lint_source('<p id="x">\n<p id="x">', rules=select_rules(["RL303"]))
    assert 'Duplicate id "x" (first used on line 1)' in violation.message


def test_every_extra_occurrence_is_reported(lint):
    assert lint('<p id="z">\n<p id="z">\n<p id="z">', "RL303") == [("RL303", 2), ("RL303", 3)]


@pytest.mark.parametrize(
    "source",
    [
        # Two separate {% if %} blocks can both render.
        '{% if a %}<p id="m">{% endif %}{% if b %}<p id="m">{% endif %}',
        # One outside any branch, one inside.
        '<p id="m">{% if a %}<p id="m">{% endif %}',
        # Same branch of the same block.
        '{% if a %}<p id="m"><p id="m">{% endif %}',
        # Comments do not create branches.
        '{# {% if a %} #}<p id="m">{# {% else %} #}<p id="m">',
        '{% comment %}{% else %}{% endcomment %}<p id="m"><p id="m">',
    ],
)
def test_duplicate_id_violations(lint, source):
    assert [code for code, _ in lint(source, "RL303")] == ["RL303"]


@pytest.mark.parametrize(
    "source",
    [
        '<p id="a"></p><p id="b"></p>',
        '<p id="A"></p><p id="a"></p>',
        '<p id=""></p><p id=""></p>',
        '<p id="{{ field.auto_id }}"></p><p id="{{ field.auto_id }}"></p>',
        '<p id="row-{{ forloop.counter }}"></p><p id="row-{{ forloop.counter }}"></p>',
        '{% if x %}<input id="email">{% else %}<input id="email" disabled>{% endif %}',
        '{% if a %}<p id="m">{% elif b %}<p id="m">{% else %}<p id="m">{% endif %}',
        '{% for i in items %}<p id="e">{% empty %}<p id="e">{% endfor %}',
        '{% for i in items %}<p id="e">{% else %}<p id="e">{% endfor %}',  # Jinja2
        '{% if a %}{% if b %}<p id="m">{% else %}<p id="m">{% endif %}{% endif %}',
        '{%- if a -%}<p id="j">{%- else -%}<p id="j">{%- endif %}',
        '<template><p id="t"></p></template><p id="t"></p>',
    ],
)
def test_duplicate_id_ok(lint, source):
    assert lint(source, "RL303") == []


# --------------------------------------------------------------------------
# RL401 form-label
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<input type="text" name="q">',
        '<input name="q" placeholder="Search">',
        '<input type="email" id="email">',
        '<label for="other">Email</label><input type="email" id="email">',
        "<select name=s><option>1</option></select>",
        "<textarea name=t></textarea>",
    ],
)
def test_form_label_violations(lint, source):
    assert [code for code, _ in lint(source, "RL401")] == ["RL401"]


@pytest.mark.parametrize(
    "source",
    [
        '<label for="email">Email</label><input type="email" id="email">',
        '<input type="email" id="email"><label for="email">Email</label>',
        "<label>Email <input type=email name=email></label>",
        '<input type="text" aria-label="Search">',
        '<input type="text" aria-labelledby="search-label">',
        '<input type="text" title="Search">',
        '<input type="hidden" name="next">',
        '<input type="submit" value="Go">',
        '<input type="reset">',
        '<input type="button" value="x">',
        '<input type="image" alt="Go" src="go.png">',
        '<input type="text" hidden>',
        "<input {{ widget.attrs }}>",
        '<input type="{{ widget.type }}" name="x">',
        '<input type="text" id="{{ field.id_for_label }}">',
        '<label for="{{ field.id_for_label }}">x</label><input type="text" id="id_name">',
    ],
)
def test_form_label_ok(lint, source):
    assert lint(source, "RL401") == []


# --------------------------------------------------------------------------
# RL501 button-name / RL502 link-name
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "<button></button>",
        '<button><i class="fa fa-trash"></i></button>',
        '<button><svg><path d="M0"/></svg></button>',
        '<button><img src="x.png"></button>',
        '<button><img src="x.png" alt=""></button>',
        '<button><span aria-hidden="true">X</span></button>',
        '<input type="button">',
        '<div role="button"></div>',
    ],
)
def test_button_name_violations(lint, source):
    assert lint(source, "RL501") == [("RL501", 1)]


@pytest.mark.parametrize(
    "source",
    [
        "<button>Save</button>",
        "<button>{{ label }}</button>",
        '<button>{% trans "Save" %}</button>',
        '<button aria-label="Delete"><i class="fa fa-trash"></i></button>',
        '<button title="Delete"><i class="fa fa-trash"></i></button>',
        '<button><img src="x.png" alt="Delete"></button>',
        "<button><svg><title>Delete</title></svg></button>",
        '<button><svg aria-label="Delete"></svg></button>',
        '<button><span class="sr-only">Delete</span><i class="fa"></i></button>',
        '<button>{% include "icons/trash.html" %}</button>',
        "<button {{ attrs }}></button>",
        '<input type="submit">',
        '<input type="button" value="Go">',
        '<div role="button" tabindex="0">Menu</div>',
    ],
)
def test_button_name_ok(lint, source):
    assert lint(source, "RL501") == []


@pytest.mark.parametrize(
    "source",
    [
        '<a href="/"></a>',
        '<a href="{% url \'home\' %}"><i class="icon-home"></i></a>',
        '<a href="/"><img src="logo.png"></a>',
        '<a href="/"><img src="logo.png" alt=""></a>',
    ],
)
def test_link_name_violations(lint, source):
    assert lint(source, "RL502") == [("RL502", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<a href="/">Home</a>',
        '<a href="/">{{ user.username }}</a>',
        '<a href="/" aria-label="Home"><i class="icon-home"></i></a>',
        '<a href="/"><img src="logo.png" alt="ACME home"></a>',
        '<a name="anchor"></a>',
        '<a id="top"></a>',
        '<a href="/">{% include "logo.html" %}</a>',
    ],
)
def test_link_name_ok(lint, source):
    assert lint(source, "RL502") == []


# --------------------------------------------------------------------------
# RL601 html-lang
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["<html><body></body></html>", '<html lang=""></html>'])
def test_html_lang_violations(lint, source):
    assert lint(source, "RL601") == [("RL601", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<html lang="en"></html>',
        '<html lang="{{ LANGUAGE_CODE }}"></html>',
        "<html {% block html_attrs %}{% endblock %}></html>",
        "<div>no html element in partial templates</div>",
    ],
)
def test_html_lang_ok(lint, source):
    assert lint(source, "RL601") == []


# --------------------------------------------------------------------------
# RL503 no-positive-tabindex
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<a href="/" tabindex="1">Home</a>',
        '<div tabindex="5">x</div>',
        '<input name="q" tabindex=" 32767 ">',
        '<button tabindex="+2">Go</button>',
        '<a href="/" tabindex="1" {{ attrs }}>Home</a>',
    ],
)
def test_positive_tabindex_violations(lint, source):
    assert lint(source, "RL503") == [("RL503", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<div tabindex="0">x</div>',
        '<div tabindex="-1">x</div>',
        '<div tabindex="00">x</div>',
        '<div tabindex="">x</div>',
        '<div tabindex="abc">x</div>',
        '<div tabindex="{{ order }}">x</div>',
        '<div tabindex="{% if a %}1{% else %}0{% endif %}">x</div>',
        "<div>no tabindex</div>",
    ],
)
def test_positive_tabindex_ok(lint, source):
    assert lint(source, "RL503") == []


def test_positive_tabindex_message(lint):
    from ramplint import lint_source, select_rules

    [violation] = lint_source('<a href="/" tabindex="3">x</a>', rules=select_rules(["RL503"]))
    assert 'tabindex="3"' in violation.message


# --------------------------------------------------------------------------
# RL602 viewport-zoom
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        "width=device-width, user-scalable=no",
        "width=device-width, user-scalable=0",
        "width=device-width,user-scalable=NO",
        "width=device-width; user-scalable = no",
        "width=device-width, maximum-scale=1",
        "width=device-width, maximum-scale=1.5",
        "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no",
    ],
)
def test_viewport_zoom_violations(lint, content):
    assert lint(f'<meta name="viewport" content="{content}">', "RL602") == [("RL602", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="viewport" content="width=device-width, user-scalable=yes">',
        '<meta name="viewport" content="width=device-width, maximum-scale=2">',
        '<meta name="viewport" content="width=device-width, maximum-scale=5">',
        '<meta name="viewport" content="width=device-width, maximum-scale={{ max_zoom }}">',
        '<meta name="viewport" content="{{ viewport }}">',
        '<meta name="viewport" content="maximum-scale=abc">',
        '<meta name="viewport" content="maximum-scale=0">',
        '<meta name="viewport" content="maximum-scale=-1">',
        '<meta name="description" content="user-scalable=no">',
        '<meta charset="utf-8">',
    ],
)
def test_viewport_zoom_ok(lint, source):
    assert lint(source, "RL602") == []


def test_viewport_zoom_reports_both_problems_once(lint):
    from ramplint import lint_source, select_rules

    source = '<meta name="Viewport" content="maximum-scale=1, user-scalable=no">'
    [violation] = lint_source(source, rules=select_rules(["RL602"]))
    assert "user-scalable=no" in violation.message
    assert "maximum-scale=1" in violation.message


# --------------------------------------------------------------------------
# RL504 anchor-is-valid
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<a href="#">Menu</a>',
        '<a href="  #  " onclick="go()">Menu</a>',
        '<a href="javascript:void(0)">Chat</a>',
        '<a href="JavaScript: openChat()">Chat</a>',
        '<a onclick="openMenu()">Menu</a>',
        '<a onClick="openMenu()" class="btn">Menu</a>',
        '<a onkeydown="handle(event)" tabindex="0">Menu</a>',
    ],
)
def test_anchor_is_valid_violations(lint, source):
    assert lint(source, "RL504") == [("RL504", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<a href="/orders/">Orders</a>',
        '<a href="#reviews">Reviews</a>',
        "<a href=\"{% url 'home' %}\">Home</a>",
        '<a href="{{ next_url }}">Continue</a>',
        '<a href="{{ base }}#">Weird but dynamic</a>',
        '<a href="mailto:hi@example.com">Email</a>',
        '<a name="top"></a>',
        '<a id="section-1"></a>',
        '<a class="placeholder">Not a link yet</a>',
        '<a {{ link_attrs }} onclick="go()">Dynamic</a>',
        '<button type="button" onclick="go()">Go</button>',
    ],
)
def test_anchor_is_valid_ok(lint, source):
    assert lint(source, "RL504") == []


# --------------------------------------------------------------------------
# RL402 autocomplete-valid
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "emial",
        "nope",
        "false",
        "street",
        "mobile street-address",  # contact type only before tel/email/impp
        "shipping",  # address type without a field
        "email email",
        "on email",
        "section- email",
        "email webauthn extra",
    ],
)
def test_autocomplete_violations(lint, value):
    assert lint(f'<input name="x" autocomplete="{value}">', "RL402") == [("RL402", 1)]


@pytest.mark.parametrize(
    "value",
    [
        "on",
        "off",
        "OFF",
        "email",
        "username",
        "new-password",
        "current-password webauthn",
        "one-time-code",
        "shipping street-address",
        "billing postal-code",
        "section-blue shipping address-line1",
        "work email",
        "home tel",
        "mobile tel-national",
        "section-a billing mobile tel",
        "cc-number",
        "  given-name  ",
        "",
        "{{ field.autocomplete }}",
        "{% if a %}email{% else %}off{% endif %}",
    ],
)
def test_autocomplete_ok(lint, value):
    assert lint(f'<input name="x" autocomplete="{value}">', "RL402") == []


def test_autocomplete_suggestion():
    from ramplint import lint_source, select_rules

    [violation] = lint_source('<input autocomplete="emial">', rules=select_rules(["RL402"]))
    assert 'did you mean "email"?' in violation.message


@pytest.mark.parametrize(
    ("value", "suggestion"),
    [
        ("emial", "email"),
        ("stret-address", "street-address"),
        ("usrname", "username"),
        # Common names that are not autofill tokens.
        ("accountname", "username"),
        ("first_name", "given-name"),
        ("lastName", "family-name"),
        ("zip", "postal-code"),
        ("phone", "tel"),
        ("e-mail", "email"),
        ("pasword", "current-password"),
    ],
)
def test_autocomplete_suggestions(value, suggestion):
    from ramplint import lint_source, select_rules

    [violation] = lint_source(f'<input autocomplete="{value}">', rules=select_rules(["RL402"]))
    assert violation.message.endswith(f'did you mean "{suggestion}"?')


def test_autocomplete_no_far_fetched_suggestion():
    from ramplint import lint_source, select_rules

    [violation] = lint_source('<input autocomplete="qwerty">', rules=select_rules(["RL402"]))
    assert "did you mean" not in violation.message
    assert violation.message.endswith('use "off" to disable autofill')


def test_autocomplete_on_select_textarea_and_form(lint):
    assert lint('<select autocomplete="contry"></select>', "RL402") == [("RL402", 1)]
    assert lint('<textarea autocomplete="street-adress"></textarea>', "RL402") == [("RL402", 1)]
    assert lint('<form autocomplete="email"></form>', "RL402") == [("RL402", 1)]
    assert lint('<form autocomplete="off"></form>', "RL402") == []
