"""Django project discovery, settings reading and cross-template checks."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pytest

from ramplint import lint_source, select_rules
from ramplint.cli import EXIT_ERROR, EXIT_OK, EXIT_VIOLATIONS, main
from ramplint.project.discovery import discover_project, find_project_root
from ramplint.project.settings import UNKNOWN, read_settings
from ramplint.project.templates import TemplateIndex, blocks
from ramplint.project.workspace import Workspace
from ramplint.template import tokens

BAD = '<img src="x.png">\n'  # one RL101 problem
GOOD = "<p>ok</p>\n"
EXTENSIONS = (".html",)


def make(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return root


def manage(module: str | None) -> str:
    if module is None:
        return "import sys\n"
    return f'import os\nos.environ.setdefault("DJANGO_SETTINGS_MODULE", "{module}")\n'


DJANGO = '"django.template.backends.django.DjangoTemplates"'
JINJA = '"django.template.backends.jinja2.Jinja2"'


def dirs(project) -> list[tuple[str, str]]:
    return [(project.relative(d.path), d.origin) for d in project.template_dirs]


# --------------------------------------------------------------------------
# Layouts
# --------------------------------------------------------------------------


@pytest.fixture
def startproject(tmp_path):
    return make(
        tmp_path,
        {
            "manage.py": manage("mysite.settings"),
            "mysite/__init__.py": "",
            "mysite/settings.py": f"""
                from pathlib import Path
                BASE_DIR = Path(__file__).resolve().parent.parent
                INSTALLED_APPS = ["django.contrib.admin", "polls.apps.PollsConfig"]
                TEMPLATES = [{{
                    "BACKEND": {DJANGO},
                    "DIRS": [BASE_DIR / "templates"],
                    "APP_DIRS": True,
                    "OPTIONS": {{"context_processors": []}},
                }}]
            """,
            "polls/__init__.py": "",
            "polls/apps.py": "",
            "polls/templates/polls/index.html": BAD,
            "templates/base.html": GOOD,
            "static/vendor/docs.html": BAD,
            "node_modules/pkg/index.html": BAD,
        },
    )


def test_startproject_layout(startproject):
    project = discover_project(startproject, environ={})
    assert project.settings_module == "mysite.settings"
    assert project.settings_source == "manage.py"
    assert project.from_settings
    assert dirs(project) == [("templates", "DIRS"), ("polls/templates", "app polls")]
    assert project.warnings == []


def test_cookiecutter_layout(tmp_path):
    root = make(
        tmp_path,
        {
            "manage.py": manage("config.settings.local"),
            "config/__init__.py": "",
            "config/settings/__init__.py": "",
            "config/settings/base.py": f"""
                from pathlib import Path
                import environ
                BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
                APPS_DIR = BASE_DIR / "shop"
                env = environ.Env()
                DJANGO_APPS = ["django.contrib.auth"]
                THIRD_PARTY_APPS = ["allauth"]
                LOCAL_APPS = ["shop.users"]
                INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
                TEMPLATES = [{{
                    "BACKEND": {DJANGO},
                    "DIRS": [str(APPS_DIR / "templates")],
                    "APP_DIRS": True,
                }}]
            """,
            "config/settings/local.py": """
                from .base import *  # noqa
                from .base import env
                DEBUG = env.bool("DEBUG", True)
                INSTALLED_APPS += ["debug_toolbar"]
            """,
            "shop/__init__.py": "",
            "shop/templates/base.html": GOOD,
            "shop/users/__init__.py": "",
            "shop/users/apps.py": "",
            "shop/users/templates/users/detail.html": GOOD,
        },
    )
    project = discover_project(root, environ={})
    assert project.settings_module == "config.settings.local"
    assert dirs(project) == [
        ("shop/templates", "DIRS"),
        ("shop/users/templates", "app shop.users"),
    ]


def test_src_layout_with_os_path(tmp_path):
    root = make(
        tmp_path,
        {
            "manage.py": manage("mysite.settings"),
            "src/mysite/__init__.py": "",
            "src/mysite/settings.py": f"""
                import os
                BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                INSTALLED_APPS = ("blog",)
                TEMPLATES = [{{"BACKEND": {DJANGO},
                    "DIRS": [os.path.join(BASE_DIR, "templates")], "APP_DIRS": True}}]
            """,
            "src/templates/base.html": GOOD,
            "src/blog/__init__.py": "",
            "src/blog/models.py": "",
            "src/blog/templates/blog/post.html": GOOD,
        },
    )
    project = discover_project(root, environ={})
    assert dirs(project) == [("src/templates", "DIRS"), ("src/blog/templates", "app blog")]


def test_apps_folder_and_loaders_option(tmp_path):
    root = make(
        tmp_path,
        {
            "manage.py": manage("settings"),
            "settings.py": f"""
                import os
                location = lambda x: os.path.join(os.path.dirname(os.path.realpath(__file__)), x)
                INSTALLED_APPS = ["apps.accounts"]
                INSTALLED_APPS.append("apps.orders")
                TEMPLATES = [{{"BACKEND": {DJANGO}, "DIRS": [location("templates")],
                    "OPTIONS": {{"loaders": [("django.template.loaders.cached.Loader", [
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                    ])]}}}}]
            """,
            "templates/base.html": GOOD,
            "apps/__init__.py": "",
            "apps/accounts/__init__.py": "",
            "apps/accounts/templates/accounts/login.html": GOOD,
            "apps/orders/__init__.py": "",
            "apps/orders/templates/orders/list.html": GOOD,
        },
    )
    project = discover_project(root, environ={})
    assert dirs(project) == [
        ("templates", "DIRS"),
        ("apps/accounts/templates", "app apps.accounts"),
        ("apps/orders/templates", "app apps.orders"),
    ]


def test_settings_package_is_guessed(tmp_path):
    root = make(
        tmp_path,
        {
            "manage.py": manage(None),
            "project/__init__.py": "",
            "project/settings/__init__.py": "",
            "project/settings/base.py": f"""
                from pathlib import Path
                BASE_DIR = Path(__file__).resolve().parent.parent.parent
                TEMPLATES = [{{"BACKEND": {DJANGO}, "DIRS": [BASE_DIR / "templates"]}}]
            """,
            "templates/base.html": GOOD,
        },
    )
    project = discover_project(root, environ={})
    assert project.settings_module == "project.settings.base"
    assert project.settings_source == "guess"
    assert dirs(project) == [("templates", "DIRS")]


def test_jinja2_backend(tmp_path):
    root = make(
        tmp_path,
        {
            "manage.py": manage("site_conf"),
            "site_conf.py": f"""
                INSTALLED_APPS = ["shop"]
                TEMPLATES = [
                    {{"BACKEND": {JINJA}, "DIRS": ["jinja2"], "APP_DIRS": True}},
                    {{"BACKEND": {DJANGO}, "DIRS": [], "APP_DIRS": True}},
                ]
            """,
            "jinja2/base.jinja": GOOD,
            "shop/__init__.py": "",
            "shop/jinja2/shop/cart.jinja": GOOD,
            "shop/templates/shop/admin.html": GOOD,
        },
    )
    project = discover_project(root, environ={})
    assert [(project.relative(d.path), d.backend) for d in project.template_dirs] == [
        ("jinja2", "jinja2"),
        ("shop/jinja2", "jinja2"),
        ("shop/templates", "django"),
    ]


def test_no_settings_falls_back_to_app_folders(tmp_path):
    root = make(
        tmp_path,
        {
            "manage.py": manage(None),
            "templates/base.html": GOOD,
            "shop/apps.py": "",
            "shop/templates/shop/list.html": GOOD,
            "docs/templates/page.html": GOOD,  # not next to an app
        },
    )
    project = discover_project(root, environ={})
    assert project.settings_module is None
    assert dirs(project) == [("templates", "fallback"), ("shop/templates", "fallback")]


def test_unreadable_values_are_reported(tmp_path):
    root = make(
        tmp_path,
        {
            "manage.py": manage("settings"),
            "settings.py": f"""
                import environ
                env = environ.Env()
                INSTALLED_APPS = ["shop", env("EXTRA_APP")]
                TEMPLATES = [
                    {{"BACKEND": {DJANGO}, "DIRS": ["templates", env("TEMPLATE_DIR")]}},
                    {{"BACKEND": "custom.Backend"}},
                    env.dict("MORE"),
                ]
            """,
            "templates/base.html": GOOD,
            "shop/apps.py": "",
            "shop/templates/shop/x.html": GOOD,
        },
    )
    project = discover_project(root, environ={})
    assert ("templates", "DIRS") in dirs(project)
    # Unreadable TEMPLATES entries: the fallback search runs as well.
    assert ("shop/templates", "fallback") in dirs(project)
    assert "an INSTALLED_APPS entry could not be read" in project.warnings
    assert "a django DIRS entry could not be read" in project.warnings
    assert "a TEMPLATES entry could not be read" in project.warnings
    assert "template backend 'custom.Backend' is not supported" in project.warnings


def test_settings_from_environment_and_override(startproject):
    make(
        startproject,
        {
            "mysite/other.py": f'TEMPLATES = [{{"BACKEND": {DJANGO}, "DIRS": ["polls"]}}]\n',
        },
    )
    project = discover_project(startproject, environ={"DJANGO_SETTINGS_MODULE": "mysite.other"})
    assert (project.settings_module, project.settings_source) == ("mysite.other", "environment")
    # An environment value from another project is ignored.
    project = discover_project(startproject, environ={"DJANGO_SETTINGS_MODULE": "elsewhere.s"})
    assert project.settings_module == "mysite.settings"
    project = discover_project(startproject, "mysite.other", "--settings", environ={})
    assert project.settings_source == "--settings"


def test_find_project_root(startproject):
    assert find_project_root(startproject / "polls" / "templates") == startproject.resolve()
    assert find_project_root(startproject.parent) is None


# --------------------------------------------------------------------------
# Settings reader
# --------------------------------------------------------------------------


def read(tmp_path, source: str, **extra: str):
    make(tmp_path, {"conf.py": source, **extra})
    return read_settings("conf", [tmp_path])


def test_settings_expressions(tmp_path):
    settings = read(
        tmp_path,
        """
        import os, os.path
        from pathlib import Path as P
        ROOT = P("/srv/app")
        A = ROOT / "a"
        B = os.path.join("/srv", "b")
        C = str(ROOT.joinpath("c"))
        D = ROOT.parents[0]
        E = f"{ROOT}/e"
        F = [*["x"], "y"] + ["z"]
        G = {"k": 1, **{"m": 2}}
        H = G["m"]
        I = "a" if True else "b"
        def join(name):
            return os.path.join("/srv", name)
        J = join("j")
        K, L = 1, 2
        M = os.path.basename("/srv/m")
        N = os.path.normpath("/srv/./n")
        O = tuple(["o"])
        Q = list(("q",))
        X = os.getcwd()
        """,
    )
    values = settings.values
    assert values["A"] == Path("/srv/app/a")
    # os.path and str(Path) use the platform's separator.
    assert values["B"] == os.path.join("/srv", "b")
    assert values["C"] == str(Path("/srv/app/c"))
    assert values["D"] == Path("/srv")
    assert values["E"] == f"{Path('/srv/app')}/e"
    assert values["F"] == ["x", "y", "z"]
    assert values["G"] == {"k": 1, "m": 2}
    assert values["H"] == 2
    assert values["I"] == "a"
    assert values["J"] == os.path.join("/srv", "j")
    assert (values["K"], values["L"]) == (1, 2)
    assert values["M"] == "m"
    assert values["N"] == os.path.normpath("/srv/./n")
    assert values["O"] == ("o",)
    assert values["Q"] == ["q"]
    assert values["X"] is UNKNOWN


def test_settings_statements(tmp_path):
    settings = read(
        tmp_path,
        """
        from .missing import *
        from parts import APPS, nothing_here
        INSTALLED_APPS = APPS + ["b"]
        INSTALLED_APPS += ["c"]
        INSTALLED_APPS.extend(["d"])
        INSTALLED_APPS.insert(0, "first")
        DEBUG = UNDEFINED_NAME
        if DEBUG:
            INSTALLED_APPS += ["debug_toolbar"]
        if False:
            INSTALLED_APPS += ["never"]
        else:
            INSTALLED_APPS += ["else"]
        try:
            from local import *
        except ImportError:
            pass
        with open("x") as fh:
            WITH = 1
        CONFIG = {}
        CONFIG["key"] = "value"
        COUNT: int = 3
        def complex_function():
            x = 1
            return x
        """,
        **{
            "parts.py": 'APPS = ["a"]\n',
            "local.py": "LOCAL = True\n_PRIVATE = 1\n",
        },
    )
    values = settings.values
    assert values["INSTALLED_APPS"] == [
        "first", "a", "b", "c", "d", "debug_toolbar", "else",
    ]  # fmt: skip
    assert values["LOCAL"] is True and "_PRIVATE" not in values
    assert values["CONFIG"] == {"key": "value"}
    assert values["COUNT"] == 3 and values["WITH"] == 1
    assert [p.name for p in settings.files] == ["parts.py", "local.py", "conf.py"]


def test_settings_unknown_values(tmp_path):
    settings = read(
        tmp_path,
        """
        import environ
        env = environ.Env()
        APPS = ["a"] + env.list("APPS")
        PATH = env.path("ROOT") / "x"
        ITEM = APPS[env("I")]
        NAME = "{}".format("x")
        """,
    )
    assert settings.values["APPS"] == ["a", UNKNOWN]
    assert settings.values["PATH"] is UNKNOWN
    assert settings.values["ITEM"] is UNKNOWN
    assert settings.values["NAME"] is UNKNOWN
    assert repr(UNKNOWN) == "UNKNOWN" and not UNKNOWN


def test_settings_syntax_error_and_cycles(tmp_path):
    make(tmp_path, {"broken.py": "TEMPLATES = [\n", "a.py": "from b import *\nA = 1\n"})
    make(tmp_path, {"b.py": "from a import *\nB = 2\n"})
    settings = read_settings("broken", [tmp_path])
    assert settings is not None and "cannot parse" in settings.warnings[0]
    # The circular import is cut: b sees no values from a, a gets b's.
    assert read_settings("a", [tmp_path]).values == {"A": 1, "B": 2}
    assert read_settings("missing", [tmp_path]) is None


# --------------------------------------------------------------------------
# Which files are linted
# --------------------------------------------------------------------------


def files(root: Path, paths=None, **options) -> list[str]:
    workspace = Workspace(EXTENSIONS, cwd=root, environ={}, **options)
    return sorted(p.as_posix() for p in workspace.files(paths))


def test_project_root_lints_template_folders_only(startproject, monkeypatch):
    assert files(startproject) == ["polls/templates/polls/index.html", "templates/base.html"]
    assert files(startproject, ["."]) == files(startproject)
    monkeypatch.chdir(startproject)
    assert main(["--no-color"]) == EXIT_VIOLATIONS  # polls/index.html, not static/


def test_no_django_walks_everything(startproject):
    found = files(startproject, django=False, skip_dirs={"node_modules"})
    assert "static/vendor/docs.html" in found


def test_explicit_files_are_always_linted(startproject):
    assert files(startproject, ["static/vendor/docs.html"]) == ["static/vendor/docs.html"]


def test_below_the_project_root_walks_the_folder(startproject):
    assert files(startproject / "polls") == ["templates/polls/index.html"]


def test_monorepo(tmp_path):
    for name in ("site_a", "site_b"):
        make(
            tmp_path / name,
            {
                "manage.py": manage("conf"),
                "conf.py": f'TEMPLATES = [{{"BACKEND": {DJANGO}, "DIRS": ["templates"]}}]\n',
                "templates/index.html": GOOD,
                "static/skip.html": BAD,
            },
        )
    make(tmp_path, {"shared/templates/email.html": GOOD})
    assert files(tmp_path) == [
        "shared/templates/email.html",
        "site_a/templates/index.html",
        "site_b/templates/index.html",
    ]


def test_settings_without_template_folders(tmp_path):
    root = make(
        tmp_path,
        {
            "manage.py": manage("conf"),
            "conf.py": f'TEMPLATES = [{{"BACKEND": {DJANGO}, "DIRS": []}}]\n',
            "static/x.html": BAD,
        },
    )
    assert files(root) == []


def test_project_without_settings_or_folders_is_walked(tmp_path):
    root = make(tmp_path, {"manage.py": manage(None), "pages/x.html": GOOD})
    assert files(root) == ["pages/x.html"]


def test_template_dirs_from_config(startproject):
    found = files(startproject, template_dirs=["templates", "missing"], config_root=startproject)
    assert found == ["templates/base.html"]


# --------------------------------------------------------------------------
# CLI and configuration
# --------------------------------------------------------------------------


def test_list_templates_text(startproject, monkeypatch, capsys):
    make(startproject, {"polls/templates/base.html": GOOD})  # hidden by templates/base.html
    monkeypatch.chdir(startproject)
    assert main(["--list-templates"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Project   .\n" in out
    assert "Settings  mysite.settings (from manage.py)" in out
    assert "  templates        DIRS       1 template\n" in out
    assert "  polls/templates  app polls  2 templates\n" in out
    assert "base.html: templates hides polls/templates" in out
    assert out.endswith("3 templates to lint.\n")


def test_list_templates_json(startproject, monkeypatch, capsys):
    monkeypatch.chdir(startproject)
    assert main(["--list-templates", "--format", "json"]) == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    [project] = data["projects"]
    assert project["settings_module"] == "mysite.settings"
    assert [d["path"] for d in project["template_dirs"]] == ["templates", "polls/templates"]
    assert data["files"] == 2


def test_list_templates_without_project(tmp_path, monkeypatch, capsys):
    make(tmp_path, {"a.html": GOOD})
    monkeypatch.chdir(tmp_path)
    assert main(["--list-templates"]) == EXIT_OK
    assert capsys.readouterr().out.startswith("No Django project found")
    assert main(["--list-templates", "--format", "sarif"]) == EXIT_ERROR


def test_list_templates_with_warnings_and_no_folders(tmp_path, monkeypatch, capsys):
    make(
        tmp_path,
        {
            "manage.py": manage("conf"),
            "conf.py": f'TEMPLATES = [{{"BACKEND": {DJANGO}, "DIRS": [X]}}]\n',
        },
    )
    monkeypatch.chdir(tmp_path)
    main(["--list-templates"])
    out = capsys.readouterr().out
    assert "No template folders found." in out
    assert "Warnings:\n  a django DIRS entry could not be read" in out


def test_verbose(startproject, monkeypatch, capsys):
    monkeypatch.chdir(startproject)
    main(["--verbose", "--no-color"])
    err = capsys.readouterr().err
    assert "ramplint: project .: mysite.settings (from manage.py)" in err
    assert "ramplint:   polls/templates [app polls]" in err
    assert "ramplint: 2 templates to lint" in err


def test_verbose_without_project(tmp_path, monkeypatch, capsys):
    make(tmp_path, {"a.html": GOOD})
    monkeypatch.chdir(tmp_path)
    main(["--verbose"])
    assert "no Django project found" in capsys.readouterr().err


def test_settings_option(startproject, monkeypatch, capsys):
    monkeypatch.chdir(startproject)
    assert main(["--settings", "nope.settings"]) == EXIT_ERROR
    assert "settings module 'nope.settings' not found" in capsys.readouterr().err


def test_config_options(startproject, monkeypatch, capsys):
    monkeypatch.chdir(startproject)
    (startproject / "pyproject.toml").write_text(
        '[tool.ramplint]\ndjango = false\nexclude = ["node_modules/*"]\n'
    )
    main(["--list-templates"])
    assert "static/vendor/docs.html" not in capsys.readouterr().out  # just a count
    (startproject / "pyproject.toml").write_text(
        '[tool.ramplint]\ndjango-settings = "mysite.settings"\n'
    )
    assert main(["--list-templates"]) == EXIT_OK
    assert "(from pyproject.toml)" in capsys.readouterr().out
    (startproject / "pyproject.toml").write_text('[tool.ramplint]\ntemplate-dirs = ["templates"]\n')
    main(["--list-templates"])
    assert "Settings  template-dirs in pyproject.toml" in capsys.readouterr().out


@pytest.mark.parametrize(
    "line",
    ['django = "yes"', "django-settings = 1", 'django-settings = " "', "template-dirs = 1"],
)
def test_bad_django_config(startproject, monkeypatch, capsys, line):
    monkeypatch.chdir(startproject)
    (startproject / "pyproject.toml").write_text(f"[tool.ramplint]\n{line}\n")
    assert main([]) == EXIT_ERROR


# --------------------------------------------------------------------------
# Template references and blocks
# --------------------------------------------------------------------------


def test_references_and_blocks():
    source = (
        '{% extends "base.html" %}{% load i18n %}'
        "{% block a %}x{% block b %}y{% endblock b %}{% endblock %}"
        "{% include name %}{% import 'macros.html' as m %}{% block open %}"
    )
    found = blocks(tokens(source))
    assert [(b.name, b.parent.name if b.parent else None) for b in found] == [
        ("a", None),
        ("b", "a"),
        ("open", None),
    ]


def test_index_order_and_chain(tmp_path):
    make(
        tmp_path,
        {
            "one/base.html": "<p>one</p>",
            "two/base.html": "<p>two</p>",
            "two/page.html": '{% extends "base.html" %}',
            "two/loop_a.html": '{% extends "loop_b.html" %}',
            "two/loop_b.html": '{% extends "loop_a.html" %}',
            "two/orphan.html": '{% extends "missing.html" %}',
        },
    )
    index = TemplateIndex([tmp_path / "one", tmp_path / "two"], EXTENSIONS)
    assert index.find("base.html") == (tmp_path / "one" / "base.html").resolve()
    assert index.find("../one/base.html") is None
    assert index.name_of(tmp_path / "two" / "page.html") == "page.html"
    assert index.name_of(tmp_path / "elsewhere.html") is None
    page = index.get("page.html")
    assert [t.path.parent.name for t in index.chain(page)] == ["one"]
    assert index.chain(index.get("loop_a.html")) == []
    assert index.chain(index.get("orphan.html")) == []
    assert index.load(tmp_path / "nope.html") is None
    assert "base.html" in index.extended


# --------------------------------------------------------------------------
# Cross-template checks
# --------------------------------------------------------------------------


BASE = """
    <!DOCTYPE html>
    <html lang="en">
    <head><title>{% block title %}{% endblock %}</title></head>
    <body>
    {% include "partials/nav.html" %}
    {% block hero %}<h2>Default hero</h2>{% endblock %}
    <main>
    <h1>Shop</h1>
    {% block content %}{% endblock %}
    </main>
    {% block footer %}{% endblock %}
    </body>
    </html>
"""


@pytest.fixture
def site(tmp_path):
    return make(
        tmp_path / "templates",
        {
            "base.html": BASE,
            "partials/nav.html": '<nav aria-label="Main"><a href="/" id="home">Home</a></nav>',
            "partials/field.html": '<input id="q" name="q" aria-label="Search">',
            "partials/dynamic.html": '<input id="{{ field_id }}" aria-label="x">',
            "partials/deep.html": '{% include "partials/field.html" %}{% include var %}',
            "layout.html": (
                '{% extends "base.html" %}'
                "{% block content %}<div>{% block body %}{% endblock %}</div>{% endblock %}"
            ),
            "page_of_layout.html": (
                '{% extends "layout.html" %}{% block body %}<p>x</p>{% endblock %}'
            ),
        },
    )


def lint_page(site: Path, name: str, source: str, *codes: str) -> list[tuple[str, int, str]]:
    path = site / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    workspace = Workspace(EXTENSIONS, cwd=site, environ={}, django=False)
    context = workspace.context_for(path)
    violations = lint_source(
        path.read_text(encoding="utf-8"), rules=select_rules(list(codes)), context=context
    )
    return [(v.code, v.line, v.message) for v in violations]


def test_heading_after_base_heading(site):
    found = lint_page(
        site,
        "shop/list.html",
        """
        {% extends "base.html" %}
        {% block title %}Shop{% endblock %}
        {% block content %}
        <h3>Products</h3>
        <h4>New</h4>
        <h6>Skipped</h6>
        {% endblock %}
        <h5>Outside any block: never rendered</h5>
        """,
        "RL301",
    )
    assert found == [
        ("RL301", 4, "Heading level skips from <h1> in base.html (line 8) to <h3>; use <h2> "
         "here or restructure the outline"),
        ("RL301", 6, "Heading level skips from <h4> to <h6>; use <h5> here or restructure "
         "the outline"),
    ]  # fmt: skip


def test_heading_baseline_uses_overridden_blocks_and_includes(site):
    make(site, {"partials/nav.html": "<nav><h3>Menu</h3></nav>"})
    found = lint_page(
        site,
        "page.html",
        """
        {% extends "base.html" %}
        {% block title %}Shop{% endblock %}
        {% block hero %}<h1>Big hero</h1>{% endblock %}
        {% block content %}<h2>Fine after the base h1</h2>{% endblock %}
        {% block footer %}<h4>After h1 of base? No: after the content block</h4>{% endblock %}
        """,
        "RL301",
    )
    # The footer comes after <main>: its baseline is the base's <h1>.
    assert [line for _, line, _ in found] == [5]


def test_heading_baseline_unknown(site):
    content = "{% block content %}<h3>x</h3>{% endblock %}"
    unknown = [
        "{% block hero %}{{ block.super }}{% endblock %}" + content,
        "{% block hero %}{% include var %}{% endblock %}" + content,
    ]
    for body in unknown:
        found = lint_page(site, "u.html", '{% extends "base.html" %}' + body, "RL301")
        assert found == [], body
    make(site, {"partials/nav.html": "{% include missing_name %}"})
    found = lint_page(
        site,
        "u2.html",
        '{% extends "base.html" %}{% block content %}<h3>x</h3>{% endblock %}',
        "RL301",
    )
    assert found == []
    # Grandchild templates: only child -> base is supported.
    found = lint_page(
        site,
        "g.html",
        '{% extends "layout.html" %}{% block body %}<h4>x</h4>{% endblock %}',
        "RL301",
    )
    assert found == []


def test_heading_with_unknown_base_uses_file_order(site):
    found = lint_page(site, "x.html", '{% extends "missing.html" %}<h2>a</h2><h4>b</h4>', "RL301")
    assert [line for _, line, _ in found] == [1]


def test_heading_before_nested_or_missing_block(site):
    for body in (
        "{% block body %}<h3>x</h3>{% endblock %}",
        "{% block nope %}<h3>x</h3>{% endblock %}",
    ):
        assert lint_page(site, "n.html", '{% extends "base.html" %}' + body, "RL301") == []


def test_heading_first_block_without_heading_before(tmp_path):
    root = make(
        tmp_path / "templates", {"base.html": "<body>{% block content %}{% endblock %}</body>"}
    )
    found = lint_page(
        root,
        "p.html",
        '{% extends "base.html" %}{% block content %}<h3>x</h3>{% endblock %}',
        "RL301",
    )
    assert found == []


def test_empty_page_title(site):
    found = lint_page(
        site,
        "shop/detail.html",
        '{% extends "base.html" %}{% block content %}x{% endblock %}',
        "RL603",
    )
    assert found == [
        ("RL603", 1, 'The page title stays empty: base.html renders <title>{% block title %}'
         '{% endblock %}</title> and nothing fills the "title" block; add {% block title %}'
         "Orders | Shop{% endblock %}"),
    ]  # fmt: skip
    empty = lint_page(
        site, "e.html", '{% extends "base.html" %}{% block title %} {% endblock %}', "RL603"
    )
    assert len(empty) == 1


@pytest.mark.parametrize(
    "source",
    [
        '{% extends "base.html" %}{% block title %}Detail{% endblock %}',
        '{% extends "base.html" %}{% block title %}{{ product.name }}{% endblock %}',
        '{% extends "missing.html" %}',
        "<p>No extends</p>",
    ],
)
def test_page_title_filled(site, source):
    assert lint_page(site, "ok.html", source, "RL603") == []


def test_page_title_of_layouts_and_bases_with_text(site, tmp_path):
    # layout.html is extended by another template, so it is not a page.
    assert lint_page(site, "layout.html", (site / "layout.html").read_text(), "RL603") == []
    # page_of_layout.html fills no title: reported through two levels.
    source = (site / "page_of_layout.html").read_text()
    assert len(lint_page(site, "page_of_layout.html", source, "RL603")) == 1
    for title in (
        "<title>{% block title %}{% endblock %} | Shop</title>",
        "<title>Shop</title>",
        "<title>{% block a %}{% endblock %}{% block b %}{% endblock %}</title>",
    ):
        other = make(
            tmp_path / title.count("block").__str__() / "templates",
            {
                "base.html": f"<html lang='en'><head>{title}</head></html>",
            },
        )
        assert lint_page(other, "p.html", '{% extends "base.html" %}', "RL603") == []


def test_main_inside_base_main(site):
    found = lint_page(
        site,
        "m.html",
        """
        {% extends "base.html" %}
        {% block title %}x{% endblock %}
        {% block content %}<main>Nested</main>{% endblock %}
        {% block footer %}<main hidden>Inactive</main><main>Second</main>{% endblock %}
        """,
        "RL306",
    )
    assert [line for _, line, _ in found] == [3, 4]
    assert found[0][2].startswith("base.html already wraps the 'content' block in <main> (line 7)")


def test_ids_from_includes_and_base(site):
    found = lint_page(
        site,
        "f.html",
        """
        {% extends "base.html" %}
        {% block content %}
        {% include "partials/field.html" %}
        <label for="q">Search</label>
        <label for="nope">Missing</label>
        <p aria-describedby="home">Refers to the nav in base.html</p>
        <p aria-describedby="nope2">Missing</p>
        {% endblock %}
        """,
        "RL403",
        "RL703",
    )
    assert [(code, line) for code, line, _ in found] == [("RL403", 5), ("RL703", 7)]


@pytest.mark.parametrize(
    "include",
    [
        '{% include "partials/dynamic.html" %}',
        '{% include "partials/deep.html" %}',
        '{% include "partials/missing.html" %}',
        "{% include template_name %}",
        "{{ form.email }}",
    ],
)
def test_ids_unknown(site, include):
    source = '{% extends "base.html" %}{% block content %}' + include
    source += '<label for="nope">x</label>{% endblock %}'
    assert lint_page(site, "u.html", source, "RL403") == []


def test_ids_with_unknown_parent(site):
    source = '{% extends "missing.html" %}{% block content %}<label for="x">x</label>{% endblock %}'
    assert lint_page(site, "u.html", source, "RL403") == []


def test_ids_include_cycle(site):
    make(
        site,
        {
            "partials/a.html": '{% include "partials/b.html" %}<i id="a"></i>',
            "partials/b.html": '{% include "partials/a.html" %}<i id="b"></i>',
        },
    )
    source = '{% include "partials/a.html" %}<label for="b">x</label><label for="c">y</label>'
    assert [line for _, line, _ in lint_page(site, "c.html", source, "RL403")] == [1]


def test_no_context_outside_template_folders(tmp_path):
    workspace = Workspace(EXTENSIONS, cwd=tmp_path, environ={}, django=False)
    make(tmp_path, {"pages/a.html": GOOD})
    assert workspace.context_for(tmp_path / "pages" / "a.html") is None


def test_context_in_project(startproject):
    workspace = Workspace(EXTENSIONS, cwd=startproject, environ={})
    context = workspace.context_for(startproject / "polls/templates/polls/index.html")
    assert context is not None
    assert context.index.dirs[0] == (startproject / "templates").resolve()


def test_settings_edge_cases(tmp_path):
    make(tmp_path, {"pkg/__init__.py": "", "pkg/sub/__init__.py": ""})
    make(tmp_path, {"pkg/common.py": "SHARED = 1\n"})
    settings = read(
        tmp_path,
        """
        import os
        from os import path as osp
        from pathlib import Path
        import json
        ROOT = Path("/srv")
        BAD_JOIN = os.path.join("/srv", 1)
        BAD_DIRNAME = os.path.dirname(1)
        BAD_PATH = Path(1)
        BAD_STR = str([1])
        BAD_LIST = list("x")
        ARITY = (lambda a: a)(1, 2)
        UNPACK_SHORT, UNPACK_OTHER = [1]
        STAR = [*env_list()]
        BAD_DIV = ROOT / 1
        BAD_ADD = 1 + "a"
        S = "a" + "b"
        T = (1,) + (2,)
        NAME = ROOT.name
        PARENTS = ROOT.parents
        UNKNOWN_ATTR = ROOT.stem
        BAD_JOINPATH = ROOT.joinpath(1)
        OTHER_METHOD = ROOT.exists()
        BAD_INDEX = [1][5]
        BAD_KEY = {"a": 1}[UNDEFINED]
        IFX = "a" if UNDEFINED else "b"
        FSTR = f"{[1]}"
        LAMBDA_NAME = osp.basename("/x/y")
        J = json.loads("{}")
        NOT_LIST = 5
        NOT_LIST.append(1)
        APPS = ["a"]
        APPS.extend(UNDEFINED)
        APPS.clear()
        UNDEFINED_OBJ.attr = 1
        SET = {"x"}
        CALLED = UNDEFINED()
        """,
    )
    v = settings.values
    for name in (
        "BAD_JOIN", "BAD_DIRNAME", "BAD_PATH", "BAD_STR", "BAD_LIST", "ARITY", "UNPACK_SHORT",
        "BAD_DIV", "BAD_ADD", "UNKNOWN_ATTR", "BAD_JOINPATH", "OTHER_METHOD", "BAD_INDEX",
        "BAD_KEY", "IFX", "FSTR", "J", "CALLED",
    ):  # fmt: skip
        assert v[name] is UNKNOWN, name
    assert v["STAR"] == [UNKNOWN]
    assert (v["S"], v["T"], v["NAME"], v["LAMBDA_NAME"]) == ("ab", (1, 2), "srv", "y")
    assert v["PARENTS"] == [Path("/")]
    assert v["APPS"] == ["a", UNKNOWN] and v["SET"] == ["x"]


def test_settings_relative_imports(tmp_path):
    make(
        tmp_path,
        {
            "proj/__init__.py": "",
            "proj/common.py": "COMMON = 1\n",
            "proj/settings/__init__.py": "from .base import *\n",
            "proj/settings/base.py": (
                "from ..common import COMMON\nfrom . import nothing\nBASE = 2\n"
            ),
        },
    )
    settings = read_settings("proj.settings", [tmp_path])
    assert settings.values == {"BASE": 2, "COMMON": 1}
    assert read_settings("proj.settings.base", [tmp_path]).get("COMMON") == 1


def test_discovery_details(tmp_path):
    root = make(
        tmp_path,
        {
            "manage.py": manage(None),
            "src/site/__init__.py": "",
            "src/site/wsgi.py": manage("site.conf"),
            "src/site/conf.py": f"""
                TEMPLATES = [{{"BACKEND": {DJANGO}, "DIRS": "not a list"}}]
                INSTALLED_APPS = UNDEFINED
            """,
            "src/templates/x.html": GOOD,
        },
    )
    project = discover_project(root, environ={})
    assert (project.settings_module, project.settings_source) == ("site.conf", "wsgi.py")
    assert "INSTALLED_APPS could not be read" in project.warnings


def test_settings_without_templates_warns(tmp_path):
    root = make(
        tmp_path,
        {"manage.py": manage("conf"), "conf.py": "DEBUG = True\n", "templates/a.html": GOOD},
    )
    project = discover_project(root, environ={})
    assert not project.from_settings
    assert "no TEMPLATES found in conf; looking for template folders" in project.warnings
    assert dirs(project) == [("templates", "fallback")]
