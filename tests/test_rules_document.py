"""Document-level rules: title, language tags, refresh and obsolete elements."""

from __future__ import annotations

import pytest

from ramplint import lint_source, select_rules


def messages(source: str, code: str) -> list[str]:
    return [v.message for v in lint_source(source, rules=select_rules([code]))]


# --------------------------------------------------------------------------
# RL603 document-title
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<html lang="en"><head><meta charset="utf-8"></head><body></body></html>',
        '<html lang="en"><body><p>No head at all</p></body></html>',
        '<html lang="en"><head><title></title></head></html>',
        '<html lang="en"><head><title>   </title></head></html>',
        '<html lang="en"><head><title>{# TODO #}</title></head></html>',
        # A <title> inside <svg> names the graphic, not the page.
        '<html lang="en"><head></head><body><svg><title>Logo</title></svg></body></html>',
    ],
)
def test_document_title_violations(lint, source):
    assert lint(source, "RL603") == [("RL603", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<html lang="en"><head><title>Shoply</title></head></html>',
        '<html lang="en"><head><title>{% block title %}{% endblock %}</title></head></html>',
        '<html lang="en"><head><title>{{ page_title }} | Shoply</title></head></html>',
        '<html lang="en"><head><title>{% trans "Orders" %}</title></head></html>',
        '<html lang="en"><head>{% block head %}{% endblock %}</head></html>',
        '<html lang="en"><head>{% include "partials/meta.html" %}</head></html>',
        '<html lang="en">{% block document %}{% endblock %}</html>',
        '<html lang="en"><head><title {{ attrs }}></title></head></html>',
        # Partials and child templates: the parent owns the <title>.
        "<title></title>",
        "<head><meta charset='utf-8'></head>",
        '{% extends "base.html" %}{% block title %}{% endblock %}',
    ],
)
def test_document_title_ok(lint, source):
    assert lint(source, "RL603") == []


def test_document_title_position_and_messages(lint):
    source = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n</head>\n</html>'
    assert lint(source, "RL603") == [("RL603", 3)]
    assert messages(source, "RL603")[0].startswith("Page has no <title>")
    empty = '<html lang="en"><head><title></title></head></html>'
    assert messages(empty, "RL603")[0].startswith("<title> is empty")


# --------------------------------------------------------------------------
# RL604 valid-lang
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<html lang="english">',
        '<html lang="ua">',
        '<html lang="en_US">',
        '<html lang="zz">',
        '<html lang="abcd">',
        '<html lang="en-">',
        '<html lang="en-us-x">',
        '<html lang="en GB">',
        '<p lang="romanian">Bună ziua</p>',
        '<span xml:lang="jp">こんにちは</span>',
        '<html lang="en" xml:lang="ro">',
    ],
)
def test_valid_lang_violations(lint, source):
    assert lint(source, "RL604") == [("RL604", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<html lang="en">',
        '<html lang="EN-gb">',
        '<html lang="uk">',
        '<html lang="ro-RO">',
        '<p lang="zh-Hant-TW">',
        '<p lang="sr-Latn">',
        '<p lang="es-419">',
        '<p lang="de-CH-1996">',
        '<p lang="haw">',
        '<p lang="en-a-bbb-x-private">',
        '<p lang="x-klingon">',
        '<p lang="i-klingon">',
        '<p lang="iw">',
        '<p lang="">',
        '<p lang=" en ">',
        '<html lang="{{ LANGUAGE_CODE }}">',
        '<html lang="{% get_current_language as LANG %}{{ LANG }}">',
        '<html lang="en" xml:lang="en-GB">',
        '<html lang="{{ LANGUAGE_CODE }}" xml:lang="ro">',
        '<html lang="en" xml:lang="">',
    ],
)
def test_valid_lang_ok(lint, source):
    assert lint(source, "RL604") == []


@pytest.mark.parametrize(
    ("value", "suggestion"),
    [
        ("english", "en"),
        ("ua", "uk"),
        ("cz", "cs"),
        ("en_US", "en-US"),
        ("ua-UA", "uk"),
        ("Ukrainian", "uk"),
    ],
)
def test_valid_lang_suggestions(value, suggestion):
    msg = messages(f'<html lang="{value}">', "RL604")[0]
    assert msg.endswith(f'did you mean "{suggestion}"?')


def test_valid_lang_no_suggestion_for_unknown_code():
    assert "did you mean" not in messages('<p lang="zz">', "RL604")[0]


def test_valid_lang_mismatch_message():
    msg = messages('<html lang="en" xml:lang="ro">', "RL604")[0]
    assert msg.startswith('lang="en" and xml:lang="ro" name different languages')


def test_valid_lang_reports_both_attributes(lint):
    source = '<html lang="english" xml:lang="english">'
    assert lint(source, "RL604") == [("RL604", 1), ("RL604", 1)]
    assert [m.split("=")[0] for m in messages(source, "RL604")] == ["lang", "xml:lang"]


# --------------------------------------------------------------------------
# RL605 meta-refresh
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        "30",
        "5; url=/new/",
        "5;URL='/new/'",
        "5, url=/new/",
        "0.5; url=/x",
        " 10 ",
        "1",
        "15; url={% url 'catalog:sale' %}",
        "15; url={{ next }}",
    ],
)
def test_meta_refresh_violations(lint, content):
    source = f'<meta http-equiv="refresh" content="{content}">'
    assert lint(source, "RL605") == [("RL605", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<meta http-equiv="refresh" content="0; url=/new/">',
        '<meta http-equiv="refresh" content="0">',
        '<meta http-equiv="refresh" content="{{ delay }}; url={{ next }}">',
        '<meta http-equiv="refresh" content="{% if slow %}5{% else %}0{% endif %}">',
        '<meta http-equiv="refresh" content="0; url={% url \'home\' %}">',
        '<meta http-equiv="refresh" content="">',
        '<meta http-equiv="refresh">',
        '<meta http-equiv="content-type" content="text/html; charset=utf-8">',
        '<meta name="refresh" content="5">',
    ],
)
def test_meta_refresh_ok(lint, source):
    assert lint(source, "RL605") == []


def test_meta_refresh_messages():
    redirect = messages('<meta http-equiv="Refresh" content="5; url=/new/">', "RL605")[0]
    assert redirect.startswith("The page redirects after 5 seconds")
    reload = messages('<meta http-equiv="refresh" content="1">', "RL605")[0]
    assert reload.startswith("The page reloads every 1 second,")


# --------------------------------------------------------------------------
# RL606 obsolete-elements
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "<marquee>Sale!</marquee>",
        "<MARQUEE behavior='alternate'>New</MARQUEE>",
        "<blink>New</blink>",
    ],
)
def test_obsolete_elements_violations(lint, source):
    assert lint(source, "RL606") == [("RL606", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<div class="marquee">{{ news }}</div>',
        '<p class="blink">New</p>',
        '<div role="marquee" aria-label="News">{{ news }}</div>',
    ],
)
def test_obsolete_elements_ok(lint, source):
    assert lint(source, "RL606") == []


def test_obsolete_elements_message():
    assert messages("<blink>x</blink>", "RL606")[0].startswith("<blink> moves or flashes content")
