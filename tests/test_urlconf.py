"""Reading Django URLconfs with ast (``--list-urls``), without Django."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ramplint.cli import EXIT_ERROR, EXIT_OK, main
from ramplint.config import ConfigError, load_config
from ramplint.project.discovery import discover_project
from ramplint.project.urls import RoutePart, UrlConf, UrlPattern, project_urlconf, read_urlconf

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "projects" / "urlconf"
DEMO = ROOT / "examples" / "django_project"


@pytest.fixture(scope="module")
def conf() -> UrlConf:
    found = project_urlconf(discover_project(FIXTURE))
    assert found is not None
    return found


def routes(conf: UrlConf) -> dict[str, str | None]:
    return {p.route: p.name for p in conf.patterns}


def test_paths_includes_and_namespaces(conf):
    found = routes(conf)
    assert found["/"] == "home"
    assert found["/blog/"] == "blog:index"  # include(module) + app_name
    assert found["/blog/<uuid:id>/"] == "blog:post"
    assert found["/blog/archive/"] == "blog:archive"  # re_path inside include
    assert found["/legacy/(?P<year>[0-9]{4})/"] == "legacy"
    assert found["/admin/"] == "admin:index"


def test_include_tuple_with_instance_namespace(conf):
    # include(("shop.urls", "shop"), namespace="store") inside i18n_patterns.
    found = routes(conf)
    assert found["/de-at/shop/"] == "store:list"
    assert found["/de-at/shop/<slug:category>/<int:pk>/"] == "store:detail"


def test_i18n_patterns_use_the_default_language(conf):
    assert routes(conf)["/de-at/legal/terms/"] == "terms"


def test_list_operations(conf):
    found = routes(conf)
    assert "/health/" in found  # .append()
    assert not any("__debug__" in route for route in found)  # debug_toolbar is ignored
    assert not any("media" in route for route in found)  # static() is ignored


def test_django_auth_urls_are_known(conf):
    found = routes(conf)
    assert found["/accounts/login/"] == "login"
    assert found["/accounts/reset/<uidb64>/<token>/"] == "password_reset_confirm"


def test_drf_router(conf):
    found = routes(conf)
    assert found["/de-at/shop/api/"] == "store:api-root"
    assert found["/de-at/shop/api/products/"] == "store:product-list"
    assert found["/de-at/shop/api/products/(?P<pk>[^/.]+)/"] == "store:product-detail"
    assert found["/de-at/shop/api/orders/"] == "store:orders-list"  # basename from the prefix


def test_pattern_details(conf):
    detail = conf.by_name("store:detail")
    assert detail.parameters == (("category", "slug"), ("pk", "int"))
    assert detail.view == "views.ProductDetail.as_view()"
    assert (detail.source, detail.line) == ("shop/urls.py", 9)
    assert not detail.is_static and not detail.is_regex
    assert conf.by_name("legacy").parameters == (("year", "regex"),)
    assert conf.by_name("nope") is None


def test_unresolved_is_listed_not_fatal(conf):
    assert conf.unresolved == [
        "mysite/urls.py:21: include('allauth.urls') is not part of the project",
        "mysite/urls.py:30: URL patterns could not be read "
        "(call to make_patterns() is not supported)",
    ]


def test_start_paths(conf):
    starts = conf.start_paths
    assert "/" in starts and "/blog/archive/" in starts and "/de-at/shop/api/orders/" in starts
    assert not any("<" in path or "(" in path for path in starts)


@pytest.mark.parametrize(
    "path, name",
    [
        ("/", "home"),
        ("/de-at/shop/shirts/4/", "store:detail"),
        ("/de-at/shop/api/products/7/", "store:product-detail"),
        ("/legacy/2020/", "legacy"),
        ("/blog/3f2b8c1e-9d4a-4b6e-8f1a-2c3d4e5f6a7b/", "blog:post"),
        ("/legacy/20/", None),
        ("/nowhere/", None),
    ],
)
def test_match(conf, path, name):
    pattern = conf.match(path)
    assert (pattern.name if pattern else None) == name


def test_route_parts():
    assert RoutePart("a/<int:pk>/").pattern() == r"a/(?:[0-9]+)/"
    assert RoutePart("<custom:x>/").pattern() == r"(?:[^/]+)/"
    assert RoutePart(r"^b/(?P<id>\d+)/(\w+)/$", regex=True).pattern() == r"b/(?:\d+)/(\w+)/"
    assert list(RoutePart(r"^(\d+)/$", regex=True).parameters()) == [("arg0", "regex")]
    pattern = UrlPattern((RoutePart(r"^about/$", regex=True),), None, None, "u.py", 1)
    assert pattern.is_static and pattern.is_regex and pattern.route == "/about/"


def test_demo_project():
    conf = project_urlconf(discover_project(DEMO))
    assert conf.module == "config.urls" and conf.unresolved == []
    assert routes(conf) == {
        "/": "catalog:list",
        "/products/<int:pk>/": "catalog:detail",
        "/api/products/": "catalog:api-products",
        "/accounts/login/": "accounts:login",
        "/accounts/logout/": "accounts:logout",
        "/accounts/profile/": "accounts:profile",
        "/admin/": "admin:index",
    }


def write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_edge_cases(tmp_path):
    root = write(
        tmp_path,
        {
            "site/__init__.py": "",
            "site/urls.py": (
                "from django.urls import include, path\n"
                "from django.urls import reverse_lazy\n"
                "extra: list = [path('x/', v, name='x')]\n"
                "urlpatterns = [\n"
                "    path(f'{p}/', v),\n"
                "    path('loop/', include('site.urls')),\n"
                "    path('none/', include('site.empty')),\n"
                "    path('broken/', include('site.broken')),\n"
                "    path('lazy/', include(reverse_lazy('x'))),\n"
                "    *extra,\n"
                "    path('only-route'),\n"
                "]\n"
                "urlpatterns += [path('y/', v)] + [path('z/', v)]\n"
                "try:\n"
                "    from site.more import more\n"
                "except ImportError:\n"
                "    more = []\n"
                "with open('x'):\n"
                "    urlpatterns.insert(0, path('w/', v))\n"
            ),
            "site/empty.py": "app_name = 'e'\n",
            "site/broken.py": "urlpatterns = [\n",
        },
    )
    conf = read_urlconf("site.urls", [root], root)
    assert [p.route for p in conf.patterns] == ["/x/", "/y/", "/z/", "/w/"]
    text = "\n".join(conf.unresolved)
    assert "site/urls.py:5: an entry was skipped (route f'{p}/' could not be read)" in text
    assert "site/urls.py:6: include('site.urls') includes itself" in text
    assert "site/empty.py: site.empty has no urlpatterns" in text
    assert "site/broken.py: cannot parse (SyntaxError)" in text
    assert "broken has no urlpatterns" not in text  # the parse error says it all
    assert "site/urls.py:9: include() could not be read (call to reverse_lazy()" in text
    assert "site/urls.py:11: an entry was skipped (path() needs a route and a view)" in text


def test_missing_root_urlconf(tmp_path):
    conf = read_urlconf("nope.urls", [tmp_path], tmp_path)
    assert conf.patterns == [] and conf.unresolved == ["ROOT_URLCONF 'nope.urls' not found"]
    root = write(tmp_path / "p", {"m/__init__.py": "", "m/urls.py": "x = 1\n"})
    assert read_urlconf("m.urls", [root], root).unresolved == [
        "m/urls.py: m.urls has no urlpatterns"
    ]


def test_project_without_root_urlconf(tmp_path):
    write(tmp_path, {"manage.py": "", "settings.py": "DEBUG = True\n"})
    assert project_urlconf(discover_project(tmp_path)) is None


def test_list_urls_text(monkeypatch, capsys):
    monkeypatch.chdir(DEMO)
    assert main(["--list-urls"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "URLconf   config.urls (ROOT_URLCONF in config.settings.dev)" in out
    assert "  /products/<int:pk>/  catalog:detail        catalog/urls.py:9\n" in out
    assert out.endswith("\n7 URL patterns, 6 without parameters.\n")


def test_list_urls_json_and_unresolved(monkeypatch, capsys):
    monkeypatch.chdir(FIXTURE)
    assert main(["--list-urls", "--format", "json"]) == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["urlconf"] == "mysite.urls"
    detail = next(p for p in data["patterns"] if p["name"] == "store:detail")
    assert detail["parameters"] == [
        {"name": "category", "converter": "slug"},
        {"name": "pk", "converter": "int"},
    ]
    assert detail["source"] == "shop/urls.py:9"
    assert len(data["unresolved"]) == 2
    assert main(["--list-urls"]) == EXIT_OK
    assert "Not read (ramplint never imports the project):" in capsys.readouterr().out


@pytest.mark.parametrize(
    "files, args, message",
    [
        ({}, ["--list-urls"], "no Django project found"),
        ({"manage.py": "", "settings.py": "X = 1\n"}, ["--list-urls"], "no ROOT_URLCONF"),
        ({}, ["--list-urls", "--format", "sarif"], "works with --format text or json"),
        ({"manage.py": ""}, ["--list-urls", "--settings", "nope"], "settings module 'nope'"),
    ],
)
def test_list_urls_errors(tmp_path, monkeypatch, capsys, files, args, message):
    write(tmp_path, files)
    monkeypatch.chdir(tmp_path)
    assert main(args) == EXIT_ERROR
    assert message in capsys.readouterr().err


def test_list_urls_empty(tmp_path, monkeypatch, capsys):
    write(
        tmp_path,
        {
            "manage.py": "",
            "settings.py": "ROOT_URLCONF = 'urls'\n",
            "urls.py": "urlpatterns = []\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    assert main(["--list-urls"]) == EXIT_OK
    assert "No URL patterns found." in capsys.readouterr().out


def test_samples_config(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[tool.ramplint.browser.samples]\n"catalog:detail" = ["/products/1/", "/products/2/"]\n'
    )
    assert load_config(path).browser == {
        "samples": {"catalog:detail": ["/products/1/", "/products/2/"]}
    }
    for bad in ('"x" = "/a/"', '"x" = ["a/"]', '"x" = []'):
        path.write_text(f"[tool.ramplint.browser.samples]\n{bad}\n")
        with pytest.raises(ConfigError, match="list of paths starting with /"):
            load_config(path)
    path.write_text('[tool.ramplint.browser]\nsamples = "x"\n')
    with pytest.raises(ConfigError, match="table of URL names"):
        load_config(path)
