"""Template source maps: annotation, the Django loader, --runserver."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ramplint import dom
from ramplint.browser.checks import merge_static
from ramplint.linter import Violation
from ramplint.sourcemap import SOURCE_ATTRIBUTE, annotate, parse_location
from ramplint.template import prepare

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "django_project"

TEMPLATE = """{% load i18n %}
<nav aria-label="{% trans 'Main' %}">
  <a href="{% url 'x' %}"{% if a %} class="on"{% endif %}>{% trans "Catalog" %}</a>
  <img src="a.png"/><br>
  <script>if (a < b) { el.innerHTML = '<b>x</b>'; }</script>
  <input title="a > b" {{ attrs }}>
  {% verbatim %}<span>{{ vue }}</span>{% endverbatim %}
  {# <i>no</i> #}
  {% comment %}<u>no</u>{% endcomment %}
  <!-- <s>no</s> -->
  <em data-rl-src="already.html:1:1">kept</em>
</nav>"""


def locations(source: str) -> list[str]:
    return re.findall(rf'{SOURCE_ATTRIBUTE}="([^"]+)"', source)


def test_annotate():
    annotated = annotate(TEMPLATE, "templates/nav.html")
    assert locations(annotated) == [
        "templates/nav.html:2:1",
        "templates/nav.html:3:3",
        "templates/nav.html:4:3",
        "templates/nav.html:4:21",
        "templates/nav.html:5:3",
        "templates/nav.html:6:3",
        "already.html:1:1",
    ]
    assert '<img src="a.png" data-rl-src="templates/nav.html:4:3"/>' in annotated
    assert "{% verbatim %}<span>{{ vue }}</span>{% endverbatim %}" in annotated
    assert "'<b>x</b>'" in annotated  # script content untouched
    # Removing the attributes gives back the template exactly.
    assert re.sub(rf' {SOURCE_ATTRIBUTE}="templates/[^"]+"', "", annotated) == TEMPLATE


def test_positions_match_the_template_linter():
    """The browser reports the same line:col the static linter reports."""
    annotated = annotate(TEMPLATE, "t.html")
    root = dom.parse(prepare(TEMPLATE).html)
    static = {f"t.html:{n.line}:{n.col}" for n in root.iter() if n.tag != "#document"}
    assert set(locations(annotated)) - {"already.html:1:1"} <= static


@pytest.mark.parametrize(
    "value, expected",
    [
        ("a/b.html:14:9", ("a/b.html", 14, 9)),
        ("C:/x/b.html:1:2", ("C:/x/b.html", 1, 2)),
        ("b.html:14", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_location(value, expected):
    assert parse_location(value) == expected


def test_merge_static_and_browser_findings():
    browser = Violation(
        "http://x/", 9, 9, "RL101", "img-alt", "m", url="http://x/", template="t.html:3:5"
    )
    other = Violation("http://x/", 2, 2, "RL502", "link-name", "m", url="http://x/")
    same = Violation("t.html", 3, 5, "RL101", "img-alt", "static message")
    only_static = Violation("t.html", 7, 1, "RL301", "heading-order", "m")
    merged = merge_static([browser, other], [same, only_static])
    assert [(v.path, v.code, v.confirmed) for v in merged] == [
        ("http://x/", "RL101", True),
        ("http://x/", "RL502", None),
        ("t.html", "RL301", None),
    ]


# -- Django -----------------------------------------------------------------------

django = pytest.importorskip("django", reason="the source map loader needs Django")


@pytest.fixture(scope="module")
def configured(tmp_path_factory):
    from django.conf import settings

    folder = tmp_path_factory.mktemp("templates")
    (folder / "page.html").write_text('<main>{% include "part.html" %}</main>\n')
    (folder / "part.html").write_text('\n<img src="x.png">\n')
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            RAMPLINT_SOURCE_ROOT=str(folder),
            TEMPLATES=[
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "DIRS": [str(folder)],
                    "OPTIONS": {
                        "loaders": [
                            (
                                "ramplint.django.SourceMapLoader",
                                ["django.template.loaders.filesystem.Loader"],
                            )
                        ]
                    },
                }
            ],
        )
        django.setup()
    return folder


def test_loader_annotates_templates_and_includes(configured):
    from django.template import engines

    html = engines["django"].get_template("page.html").render({})
    assert html == (
        '<main data-rl-src="page.html:1:1">\n'
        '<img src="x.png" data-rl-src="part.html:2:1">\n'
        "</main>\n"
    )


def test_loader_does_nothing_without_debug(configured, settings_debug_off):
    from django.template import engines

    engine = engines["django"].engine
    for loader in engine.template_loaders:
        loader.reset()
    assert SOURCE_ATTRIBUTE not in engines["django"].get_template("page.html").render({})


@pytest.fixture
def settings_debug_off(configured):
    from django.conf import settings

    settings.DEBUG = False
    yield
    settings.DEBUG = True


def test_loader_skips_templates_outside_the_project(configured, tmp_path):
    from ramplint.django import SourceMapLoader

    loader = SourceMapLoader.__new__(SourceMapLoader)
    loader.root = configured
    assert loader._project_path(str(configured / "a" / "b.html")) == "a/b.html"
    assert loader._project_path(str(tmp_path / "c.html")) is None
    installed = configured / "venv" / "site-packages" / "django" / "input.html"
    assert loader._project_path(str(installed)) is None


def test_wrap_template_loaders():
    from ramplint.django import wrap_template_loaders

    templates = [
        {"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True},
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "OPTIONS": {"loaders": [("django.template.loaders.cached.Loader", ["x.Loader"])]},
        },
        {"BACKEND": "django.template.backends.jinja2.Jinja2", "APP_DIRS": True},
    ]
    wrapped = wrap_template_loaders(templates)
    assert wrapped[0]["APP_DIRS"] is False
    assert wrapped[0]["OPTIONS"]["loaders"] == [
        (
            "ramplint.django.SourceMapLoader",
            [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
        )
    ]
    assert wrapped[1]["OPTIONS"]["loaders"] == [
        (
            "ramplint.django.SourceMapLoader",
            [("django.template.loaders.cached.Loader", ["x.Loader"])],
        )
    ]
    assert wrapped[2] == templates[2]  # Jinja2 is left alone
    assert "OPTIONS" not in templates[0]  # the original is not changed


# -- the development server ---------------------------------------------------------

try:
    import jinja2  # noqa: F401 - the demo project has a Jinja2 backend
except ImportError:  # pragma: no cover
    HAS_JINJA2 = False
else:
    HAS_JINJA2 = True
needs_jinja2 = pytest.mark.skipif(not HAS_JINJA2, reason="the demo project needs Jinja2")


@needs_jinja2
def test_dev_server_serves_annotated_pages(tmp_path):
    import urllib.request

    from ramplint.django.runserver import DevServer

    with DevServer(DEMO, "config.settings.dev") as server:
        html = urllib.request.urlopen(server.url, timeout=10).read().decode()
        assert 'data-rl-src="templates/base.html:3:1"' in html
        assert 'data-rl-src="catalog/templates/catalog/product_list.html:' in html
        # The server's log is captured (its wording changes between Django versions).
        assert '"GET / HTTP/1.1" 200' in server.output
    assert server.output == ""  # cleaned up


def test_dev_server_that_fails(tmp_path):
    from ramplint.django.runserver import DevServer, ServerError

    (tmp_path / "manage.py").write_text("import sys\nprint('boom')\nsys.exit(3)\n")
    with pytest.raises(ServerError, match="the server stopped:\nboom"), DevServer(tmp_path, "x"):
        pass


def test_dev_server_that_never_answers(tmp_path):
    from ramplint.django.runserver import DevServer, ServerError

    (tmp_path / "manage.py").write_text("import time\nprint('waiting')\ntime.sleep(30)\n")
    server = DevServer(tmp_path, "x", start_timeout=1)
    with pytest.raises(ServerError, match="did not answer within 1s:\nwaiting"), server:
        pass


def test_runserver_needs_a_project(tmp_path, monkeypatch, capsys):
    from ramplint.cli import EXIT_ERROR, main

    monkeypatch.chdir(tmp_path)
    assert main(["--runserver"]) == EXIT_ERROR
    assert "--runserver needs a Django project" in capsys.readouterr().err
    assert main(["--runserver", "http://x/"]) == EXIT_ERROR
    assert "do not pass paths or URLs" in capsys.readouterr().err
