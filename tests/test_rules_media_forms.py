"""Media rules (RL103-RL106), label targets (RL403) and access keys (RL506)."""

from __future__ import annotations

import pytest

from ramplint import lint_source, select_rules
from ramplint.template import MARKUP, TEXT, prepare


def messages(source: str, code: str) -> list[str]:
    return [v.message for v in lint_source(source, rules=select_rules([code]))]


# --------------------------------------------------------------------------
# Template variables that render HTML
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "{{ form }}",
        "{{ form.email }}",
        "{{ user_form.email }}",
        "{{ form.as_p }}",
        "{{ form.as_div }}",
        "{{ formset }}",
        "{{ formset.management_form }}",
        "{{ inline_formset.empty_form }}",
        "{{ field }}",
        "{{ bound_field }}",
        "{{ field.label_tag }}",
        "{{ field.errors }}",
        "{{ form.non_field_errors }}",
        "{{ form.email|as_crispy_field }}",
        "{{ form|crispy }}",
        "{{ article.body|safe }}",
        "{{- form.email -}}",
    ],
)
def test_variables_that_render_markup(token):
    assert prepare(token).html.startswith(MARKUP)


@pytest.mark.parametrize(
    "token",
    [
        "{{ product.name }}",
        "{{ form_title }}",
        "{{ platform }}",
        "{{ form.email.label }}",
        "{{ form.email.id_for_label }}",
        "{{ form.email.value }}",
        "{{ field.label }}",
        "{{ field.help_text }}",
        "{{ form.fields.email }}",
        "{{ price|floatformat:2 }}",
        "{{ items[0] }}",
    ],
)
def test_variables_that_render_text(token):
    assert prepare(token).html.startswith(TEXT)


# --------------------------------------------------------------------------
# RL103 video-caption
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<video src="intro.mp4" controls></video>',
        '<video controls><source src="{{ video.url }}" type="video/mp4"></video>',
        '<video controls><track kind="descriptions" src="d.vtt"></video>',
        '<video controls><track kind="chapters" src="c.vtt"></video>',
        '<video controls><p>{% trans "Your browser does not support video." %}</p></video>',
        '<video autoplay loop src="bg.mp4"></video>',
    ],
)
def test_video_caption_violations(lint, source):
    assert lint(source, "RL103") == [("RL103", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<video controls><track kind="captions" src="c.vtt" srclang="en"></video>',
        '<video controls><track kind="Subtitles" src="s.vtt" srclang="ro"></video>',
        '<video controls><track src="s.vtt" srclang="en"></video>',
        '<video controls><track kind="{{ track.kind }}" src="{{ track.url }}"></video>',
        "<video controls><track {{ track_attrs }}></video>",
        '<video autoplay muted loop playsinline src="bg.mp4"></video>',
        '<video controls>{% include "videos/tracks.html" %}</video>',
        "<video controls>{{ tracks_html }}</video>",
        '<video controls>{% for t in video.tracks %}<track kind="captions" src="{{ t.url }}">'
        "{% endfor %}</video>",
        "<video {{ attrs }}></video>",
        '<video aria-hidden="true" src="decor.mp4"></video>',
        '<template><video src="x.mp4"></video></template>',
    ],
)
def test_video_caption_ok(lint, source):
    assert lint(source, "RL103") == []


# --------------------------------------------------------------------------
# RL104 svg-img-alt
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<svg role="img" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>',
        '<svg role="img"><title></title><path d=""/></svg>',
        '<svg role="img"><g><title>Not a direct child</title></g></svg>',
        '<svg role="IMG"><path d=""/></svg>',
        '<svg role="img" aria-label=""><path d=""/></svg>',
    ],
)
def test_svg_img_alt_violations(lint, source):
    assert lint(source, "RL104") == [("RL104", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<svg role="img"><title>Cart</title><path d=""/></svg>',
        '<svg role="img"><title>{% trans "Cart" %}</title></svg>',
        '<svg role="img"><title>{{ icon.name }}</title></svg>',
        '<svg role="img" aria-label="Cart"></svg>',
        '<svg role="img" aria-labelledby="cart-title"><text id="cart-title">Cart</text></svg>',
        '<svg role="img" aria-hidden="true"></svg>',
        '<svg role="img">{% include "icons/cart.svg" %}</svg>',
        '<svg role="{{ role }}"></svg>',
        "<svg {{ attrs }}></svg>",
        '<svg class="icon"><use href="#cart"></use></svg>',
        '<svg role="presentation"></svg>',
    ],
)
def test_svg_img_alt_ok(lint, source):
    assert lint(source, "RL104") == []


# --------------------------------------------------------------------------
# RL105 object-alt
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<object data="{% static \'prices.pdf\' %}" type="application/pdf"></object>',
        '<object data="map.svg"><param name="zoom" value="2"></object>',
        '<object data="chart.svg"><img src="chart.png" alt=""></object>',
        '<embed src="prices.pdf" type="application/pdf">',
        '<embed src="prices.pdf" aria-label="">',
    ],
)
def test_object_alt_violations(lint, source):
    assert lint(source, "RL105") == [("RL105", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<object data="prices.pdf"><a href="prices.pdf">Download the price list (PDF)</a></object>',
        '<object data="chart.svg"><img src="chart.png" alt="Sales by month"></object>',
        '<object data="prices.pdf" aria-label="Price list (PDF)"></object>',
        '<object data="prices.pdf" title="Price list"></object>',
        "<object data=\"x.pdf\">{% trans 'Download the file' %}</object>",
        '<object data="x.pdf">{% include "fallback.html" %}</object>',
        '<embed src="prices.pdf" title="Price list (PDF)">',
        '<embed src="prices.pdf" aria-labelledby="prices-heading">',
        '<embed src="tracker.swf" aria-hidden="true">',
        '<object data="decor.svg" role="presentation"></object>',
        "<object {{ attrs }}></object>",
        "<embed {{ attrs }}>",
    ],
)
def test_object_alt_ok(lint, source):
    assert lint(source, "RL105") == []


def test_object_alt_messages():
    assert messages('<object data="a.pdf"></object>', "RL105")[0].startswith("<object> has no")
    assert messages('<embed src="a.pdf">', "RL105")[0].startswith("<embed> has no")


# --------------------------------------------------------------------------
# RL106 media-autoplay
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<video autoplay src="promo.mp4"></video>',
        '<video autoplay controls><track kind="captions" src="c.vtt"></video>',
        '<audio autoplay src="jingle.mp3"></audio>',
        '<audio autoplay="autoplay" loop src="jingle.mp3"></audio>',
    ],
)
def test_media_autoplay_violations(lint, source):
    assert lint(source, "RL106") == [("RL106", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<video autoplay muted loop src="bg.mp4"></video>',
        '<audio controls src="podcast.mp3"></audio>',
        '<video controls src="intro.mp4"></video>',
        '<video autoplay="{{ autoplay }}" src="x.mp4"></video>',
        "<video {{ attrs }} autoplay></video>",
        '<template><audio autoplay src="x.mp3"></audio></template>',
    ],
)
def test_media_autoplay_ok(lint, source):
    assert lint(source, "RL106") == []


def test_media_autoplay_message():
    msg = messages('<audio autoplay src="a.mp3"></audio>', "RL106")[0]
    assert msg.startswith("<audio autoplay> plays sound on its own")


# --------------------------------------------------------------------------
# RL403 label-for-target
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<label for="email">Email</label><input type="email" name="email">',
        '<label for="emial">Email</label><input id="email">',
        '<label for="">Email</label><input id="email">',
        '<label for="phone">Phone</label>',
        '<label for=" phone ">Phone</label><input id="tel">',
    ],
)
def test_label_for_target_violations(lint, source):
    assert lint(source, "RL403") == [("RL403", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<label for="email">Email</label><input id="email">',
        '<label for=" email ">Email</label><input id="email">',
        '<input id="email"><label for="email">Email</label>',
        '<label for="{{ form.email.id_for_label }}">Email</label>',
        # The target may be rendered somewhere ramplint cannot see.
        '<label for="id_email">Email</label>{{ form.email }}',
        '<label for="id_email">Email</label>{{ form.email|as_crispy_field }}',
        '<label for="id_email">Email</label>{% render_field form.email %}',
        '<label for="email">Email</label>{% include "fields/email.html" %}',
        '<label for="email">Email</label>{% block email_field %}{% endblock %}',
        '<label for="email">Email</label><input id="{{ field_id }}">',
        '<label for="email">Email</label><input {{ widget.attrs }}>',
        "<label>Email <input name='email'></label>",
        '<template><label for="x">X</label></template>',
    ],
)
def test_label_for_target_ok(lint, source):
    assert lint(source, "RL403") == []


def test_label_for_target_hints():
    by_name = messages('<label for="email">E</label><input name="email">', "RL403")[0]
    assert by_name.endswith('add id="email" to the <input name="email">')
    typo = messages('<label for="emial">E</label><input id="email">', "RL403")[0]
    assert typo.endswith('did you mean "email"?')
    empty = messages('<label for="">E</label>', "RL403")[0]
    assert empty.startswith('<label for=""> is empty')
    plain = messages('<label for="phone">P</label>', "RL403")[0]
    assert plain.endswith("clicking the label does nothing")


# --------------------------------------------------------------------------
# RL506 duplicate-accesskey
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<a href="/" accesskey="h">Home</a>\n<a href="/help" accesskey="h">Help</a>',
        '<a href="/" accesskey="s">Search</a>\n<button accesskey="S">Save</button>',
        '<a href="/" accesskey=" s ">Search</a>\n<input accesskey="s" aria-label="Q">',
        '{% if a %}<a href="/" accesskey="s">A</a>{% endif %}\n<a href="/" accesskey="s">B</a>',
    ],
)
def test_duplicate_accesskey_violations(lint, source):
    assert lint(source, "RL506") == [("RL506", 2)]


@pytest.mark.parametrize(
    "source",
    [
        '<a href="/" accesskey="h">Home</a><a href="/search" accesskey="s">Search</a>',
        '{% if user %}<a href="/" accesskey="a">Account</a>{% else %}'
        '<a href="/login" accesskey="a">Log in</a>{% endif %}',
        '<a href="/" accesskey="{{ key }}">A</a><a href="/" accesskey="{{ key }}">B</a>',
        '<a href="/" accesskey="">A</a><a href="/" accesskey="">B</a>',
        '<template><a accesskey="s">A</a></template><a href="/" accesskey="s">B</a>',
    ],
)
def test_duplicate_accesskey_ok(lint, source):
    assert lint(source, "RL506") == []


def test_duplicate_accesskey_message():
    msg = messages('<a accesskey="s">A</a>\n<a accesskey="s">B</a>', "RL506")[0]
    assert msg.startswith('accesskey="s" is already used on line 1')


def test_every_extra_accesskey_is_reported(lint):
    source = '<a accesskey="s">A</a>\n<a accesskey="s">B</a>\n<a accesskey="s">C</a>'
    assert lint(source, "RL506") == [("RL506", 2), ("RL506", 3)]
