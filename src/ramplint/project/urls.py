"""Read a Django URLconf without importing it.

The crawler needs every page a project has, also the ones no link points to.
Like the settings, URL modules are read with a small interpreter over the
``ast``: ``path()``, ``re_path()``, ``url()``, ``include()``,
``i18n_patterns()``, DRF routers and the list operations ``urlpatterns`` is
built with. Nothing is imported, so reading never runs project code. Whatever
cannot be followed statically is listed in :attr:`UrlConf.unresolved`.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from ramplint.project.discovery import Project, module_roots
from ramplint.project.settings import SettingsReader

#: Regular expressions of Django's built-in path converters.
CONVERTERS = {
    "int": r"[0-9]+",
    "str": r"[^/]+",
    "slug": r"[-a-zA-Z0-9_]+",
    "uuid": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    "path": r".+",
}

_CONVERTER_RE = re.compile(r"<(?:(?P<converter>[^>:]+):)?(?P<name>\w+)>")
_NAMED_GROUP_RE = re.compile(r"\(\?P<(?P<name>\w+)>")
_LITERAL_RE = re.compile(r"[\w./-]*")
_DEFAULT_LANGUAGE = "en-us"
_MAX_DEPTH = 30
#: Scope key of the module that produced a scope.
_MODULE = "__ramplint_module__"


# -- result --------------------------------------------------------------------


@dataclass(frozen=True)
class RoutePart:
    """One piece of a route as written: a ``path()`` route or a regex."""

    text: str
    regex: bool = False

    @property
    def display(self) -> str:
        if not self.regex:
            return self.text
        return self.text.removeprefix("^").removesuffix("$").removesuffix(r"\Z")

    def pattern(self) -> str:
        """The part as a regular expression without named groups."""
        if self.regex:
            return _NAMED_GROUP_RE.sub("(?:", self.display)
        pieces, position = [], 0
        for match in _CONVERTER_RE.finditer(self.text):
            pieces.append(re.escape(self.text[position : match.start()]))
            converter = match.group("converter") or "str"
            pieces.append(f"(?:{CONVERTERS.get(converter, CONVERTERS['str'])})")
            position = match.end()
        pieces.append(re.escape(self.text[position:]))
        return "".join(pieces)

    def parameters(self) -> Iterator[tuple[str, str]]:
        if self.regex:
            for match in _NAMED_GROUP_RE.finditer(self.display):
                yield match.group("name"), "regex"
            unnamed = self.display.count("(") - self.display.count("(?")
            for index in range(unnamed):
                yield f"arg{index}", "regex"
        else:
            for match in _CONVERTER_RE.finditer(self.text):
                yield match.group("name"), match.group("converter") or "str"


@dataclass(frozen=True)
class UrlPattern:
    """A page (or endpoint) of the project, with everything that leads to it."""

    parts: tuple[RoutePart, ...]
    #: ``namespace:name`` as used with ``{% url %}``, or ``None``.
    name: str | None
    #: The view expression as written (``views.ProductDetail.as_view()``).
    view: str | None
    #: File (relative to the project) and line of the ``path()`` call.
    source: str
    line: int

    @cached_property
    def route(self) -> str:
        """``/products/<int:pk>/``: the route as a Django developer reads it."""
        return "/" + "".join(part.display for part in self.parts)

    @cached_property
    def parameters(self) -> tuple[tuple[str, str], ...]:
        return tuple(p for part in self.parts for p in part.parameters())

    @property
    def is_regex(self) -> bool:
        return any(part.regex for part in self.parts)

    @cached_property
    def is_static(self) -> bool:
        """No parameters: the route is itself a URL that can be opened."""
        if self.parameters:
            return False
        return all(_LITERAL_RE.fullmatch(part.display) for part in self.parts if part.regex)

    @cached_property
    def regex(self) -> re.Pattern[str]:
        return re.compile("".join(part.pattern() for part in self.parts))

    def matches(self, path: str) -> bool:
        """Does a URL path (``/products/42/``) belong to this pattern?"""
        return self.regex.fullmatch(path.lstrip("/")) is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "name": self.name,
            "view": self.view,
            "parameters": [{"name": n, "converter": c} for n, c in self.parameters],
            "regex": self.is_regex,
            "source": f"{self.source}:{self.line}",
        }


@dataclass
class UrlConf:
    #: ``ROOT_URLCONF``.
    module: str
    patterns: list[UrlPattern] = field(default_factory=list)
    #: What could not be read statically, as ``file:line: reason``.
    unresolved: list[str] = field(default_factory=list)

    def match(self, path: str) -> UrlPattern | None:
        """The first pattern a URL path matches, in URLconf order like Django."""
        return next((p for p in self.patterns if p.matches(path)), None)

    def by_name(self, name: str) -> UrlPattern | None:
        return next((p for p in self.patterns if p.name == name), None)

    @property
    def start_paths(self) -> list[str]:
        """URL paths of the patterns without parameters."""
        return list(dict.fromkeys(p.route for p in self.patterns if p.is_static))


# -- values of the interpreter --------------------------------------------------


@dataclass(frozen=True)
class _Unresolved:
    """A value that cannot be computed, why, and the line it comes from."""

    reason: str
    line: int = 0

    def __bool__(self) -> bool:
        return False


@dataclass(frozen=True)
class _Function:
    """A Django (or DRF) function the URLconf calls; ``kind`` says which."""

    kind: str


@dataclass(frozen=True)
class _ModuleRef:
    """A module imported by name (``from catalog import urls``)."""

    name: str


@dataclass(frozen=True)
class _Where:
    source: str
    line: int


@dataclass
class _Leaf:
    part: RoutePart
    name: str | None
    view: str | None
    where: _Where


@dataclass
class _Included:
    """What ``include()`` returns: patterns plus their application namespace."""

    entries: list[Any]
    namespace: str | None = None


@dataclass
class _Branch:
    part: RoutePart
    included: _Included
    where: _Where


@dataclass
class _Router:
    root_view: bool
    trailing_slash: str
    registered: list[tuple[str, str, str, _Where]] = field(default_factory=list)


@dataclass(frozen=True)
class _RouterUrls:
    router: _Router


_KNOWN: dict[str, Any] = {
    "django.urls.path": _Function("path"),
    "django.urls.re_path": _Function("re_path"),
    "django.conf.urls.url": _Function("re_path"),
    "django.urls.include": _Function("include"),
    "django.conf.urls.include": _Function("include"),
    "django.conf.urls.i18n.i18n_patterns": _Function("i18n_patterns"),
    "django.conf.urls.static.static": _Function("ignored"),
    "django.contrib.staticfiles.urls.staticfiles_urlpatterns": _Function("ignored"),
    "debug_toolbar.toolbar.debug_toolbar_urls": _Function("ignored"),
    "rest_framework.routers.DefaultRouter": _Function("default_router"),
    "rest_framework.routers.SimpleRouter": _Function("simple_router"),
    "django.contrib.admin": _ModuleRef("django.contrib.admin"),
}

#: Modules that are only used in development and never hold pages to check.
_IGNORED_MODULES = ("debug_toolbar", "django_browser_reload", "silk", "__debug__")

#: URLconfs that ship with Django: their routes, without reading Django itself.
_BUILTIN_URLCONFS: dict[str, list[tuple[str, str]]] = {
    "django.contrib.auth.urls": [
        ("login/", "login"),
        ("logout/", "logout"),
        ("password_change/", "password_change"),
        ("password_change/done/", "password_change_done"),
        ("password_reset/", "password_reset"),
        ("password_reset/done/", "password_reset_done"),
        ("reset/<uidb64>/<token>/", "password_reset_confirm"),
        ("reset/done/", "password_reset_complete"),
    ],
}

_LIST_METHODS = ("append", "extend", "insert")


# -- interpreter ----------------------------------------------------------------


class _UrlModule:
    """Evaluates one URL module into its ``urlpatterns`` and ``app_name``."""

    def __init__(self, reader: UrlConfReader, name: str, path: Path, depth: int) -> None:
        self.reader = reader
        self.name = name
        self.path = path
        self.depth = depth
        self.source = reader.relative(path)
        self.scope: dict[str, Any] = {}
        self.failed = False

    def run(self) -> dict[str, Any]:
        self.scope[_MODULE] = self
        try:
            tree = ast.parse(self.path.read_text(encoding="utf-8"), filename=str(self.path))
        except (OSError, SyntaxError, ValueError) as exc:
            self.reader.unresolved(f"{self.source}: cannot parse ({exc.__class__.__name__})")
            self.failed = True
            return self.scope
        self._run_body(tree.body)
        return self.scope

    def urlpatterns(self) -> tuple[list[Any], str | None] | None:
        """The module's checked ``urlpatterns`` and ``app_name``; ``None`` without them."""
        patterns = self.scope.get("urlpatterns")
        if patterns is None:
            if not self.failed:
                self.reader.unresolved(f"{self.source}: {self.name} has no urlpatterns")
            return None
        app_name = self.scope.get("app_name")
        return self._entries(patterns, None), app_name if isinstance(app_name, str) else None

    # -- statements ------------------------------------------------------------
    def _run_body(self, body: Sequence[ast.stmt]) -> None:
        for statement in body:
            self._run(statement)

    def _run(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Assign):
            value = self.evaluate(node.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.scope[target.id] = value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                self.scope[node.target.id] = self.evaluate(node.value)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            current = self.scope.get(node.target.id)
            added = self.evaluate(node.value)
            if isinstance(current, list) and isinstance(node.op, ast.Add):
                current.extend(self._entries(added, node))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            self._import(node)
        elif isinstance(node, ast.If):
            # ``if settings.DEBUG:`` usually adds development URLs, which are
            # ignored anyway; anything else is better seen than missed.
            self._run_body(node.body)
            self._run_body(node.orelse)
        elif isinstance(node, ast.Try):
            self._run_body([*node.body, *node.orelse, *node.finalbody])
        elif isinstance(node, ast.With):
            self._run_body(node.body)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            self._statement_call(node.value)

    def _statement_call(self, call: ast.Call) -> None:
        """``urlpatterns.append(...)``, ``.extend(...)`` and ``router.register(...)``."""
        func = call.func
        if not isinstance(func, ast.Attribute):
            return
        owner = self.evaluate(func.value)
        if isinstance(owner, _Router) and func.attr == "register":
            self._register(owner, call)
        elif isinstance(owner, list) and func.attr in _LIST_METHODS and call.args:
            value = self.evaluate(call.args[-1])
            if func.attr == "extend":
                owner.extend(self._entries(value, call))
            else:
                owner.extend(self._entries([value], call))

    def _register(self, router: _Router, call: ast.Call) -> None:
        prefix = self.evaluate(call.args[0]) if call.args else None
        if not isinstance(prefix, str):
            self.reader.unresolved(f"{self._at(call)}: router prefix could not be read")
            return
        view = ast.unparse(call.args[1]) if len(call.args) > 1 else ""
        basename = self._keyword(call, "basename", 2)
        if not isinstance(basename, str):
            basename = prefix.strip("/").replace("/", "-")
        router.registered.append((prefix, view, basename, self._where(call)))

    def _import(self, node: ast.Import | ast.ImportFrom) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    self.scope[alias.asname] = self._module_value(alias.name)
                else:
                    top = alias.name.split(".")[0]
                    self.scope[top] = self._module_value(top)
            return
        module = self._absolute(node.module or "", node.level)
        for alias in node.names:
            if alias.name == "*":
                values = self.reader.module_scope(module, self.depth + 1)
                if values:
                    self.scope.update({k: v for k, v in values.items() if not k.startswith("_")})
                continue
            self.scope[alias.asname or alias.name] = self._imported(module, alias.name)

    def _imported(self, module: str, name: str) -> Any:
        dotted = f"{module}.{name}"
        if dotted in _KNOWN:
            return _KNOWN[dotted]
        if self.reader.finder.find_module(dotted) is not None:
            return _ModuleRef(dotted)
        values = self.reader.module_scope(module, self.depth + 1)
        if values is not None and name in values:
            return values[name]
        if values is None:
            return _ModuleRef(dotted)
        return _Unresolved(f"{name} is not defined in {module}")

    def _module_value(self, module: str) -> Any:
        return _KNOWN.get(module, _ModuleRef(module))

    def _absolute(self, module: str, level: int) -> str:
        if level == 0:
            return module
        package = self.name.split(".")
        if self.path.name != "__init__.py":
            package = package[:-1]
        if level > 1:
            package = package[: len(package) - (level - 1)]
        return ".".join([*package, module] if module else package)

    # -- expressions -----------------------------------------------------------
    def evaluate(self, node: ast.expr) -> Any:
        value = self._evaluate(node)
        if isinstance(value, _Unresolved) and not value.line:
            return _Unresolved(value.reason, getattr(node, "lineno", 0))
        return value

    def _evaluate(self, node: ast.expr) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return _Unresolved("f-string route")
        if isinstance(node, ast.Name):
            return self.scope.get(node.id, _Unresolved(f"{node.id} is not defined here"))
        if isinstance(node, (ast.List, ast.Tuple)):
            items: list[Any] = []
            for element in node.elts:
                if isinstance(element, ast.Starred):
                    items.extend(self._entries(self.evaluate(element.value), element))
                else:
                    items.append(self.evaluate(element))
            return tuple(items) if isinstance(node, ast.Tuple) else items
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = self.evaluate(node.left), self.evaluate(node.right)
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            return [*self._entries(left, node), *self._entries(right, node)]
        if isinstance(node, ast.Attribute):
            return self._attribute(self.evaluate(node.value), node)
        if isinstance(node, ast.Call):
            return self._call(node)
        return _Unresolved(f"{ast.unparse(node)} is not supported")

    def _attribute(self, owner: Any, node: ast.Attribute) -> Any:
        attr = node.attr
        if isinstance(owner, _ModuleRef):
            dotted = f"{owner.name}.{attr}"
            if dotted == "django.contrib.admin.site":
                return _ModuleRef(dotted)
            if dotted == "django.contrib.admin.site.urls":
                return _Included([_admin_index(self._where(node))], "admin")
            if dotted in _KNOWN:
                return _KNOWN[dotted]
            values = self.reader.module_scope(owner.name, self.depth + 1)
            if values is not None and attr in values:
                return values[attr]
            return _ModuleRef(dotted)
        if isinstance(owner, _Router) and attr == "urls":
            return _RouterUrls(owner)
        return _Unresolved(f"attribute {attr} is not supported")

    def _call(self, call: ast.Call) -> Any:
        func = self.evaluate(call.func)
        if not isinstance(func, _Function):
            return _Unresolved(f"call to {ast.unparse(call.func)}() is not supported")
        kind = func.kind
        if kind in ("path", "re_path"):
            return self._path(call, regex=kind == "re_path")
        if kind == "include":
            return self._include(call)
        if kind == "i18n_patterns":
            return self._i18n(call)
        if kind in ("default_router", "simple_router"):
            slash = self._keyword(call, "trailing_slash", 0)
            return _Router(
                root_view=kind == "default_router",
                trailing_slash="" if slash is False else "/",
            )
        return []  # ignored helpers such as static()

    def _path(self, call: ast.Call, *, regex: bool) -> Any:
        if len(call.args) < 2:
            return _Unresolved("path() needs a route and a view")
        route = self.evaluate(call.args[0])
        if not isinstance(route, str):
            return _Unresolved(f"route {ast.unparse(call.args[0])} could not be read")
        part = RoutePart(route, regex=regex)
        target = self.evaluate(call.args[1])
        where = self._where(call)
        if isinstance(target, _Included):
            return _Branch(part, target, where)
        if isinstance(target, _RouterUrls):
            return _Branch(part, _Included([target]), where)
        name = self._keyword(call, "name", 3)
        view = ast.unparse(call.args[1])
        return _Leaf(part, name if isinstance(name, str) else None, view, where)

    def _include(self, call: ast.Call) -> Any:
        if not call.args:
            return _Unresolved("include() without arguments")
        target = self.evaluate(call.args[0])
        namespace = self._keyword(call, "namespace", 1)
        app_name: str | None = None
        if isinstance(target, tuple) and len(target) == 2:
            target, app_name = target
        if isinstance(target, _ModuleRef):
            target = target.name
        if isinstance(target, str):
            entries, module_app_name = self.reader.include_module(target, call, self)
            app_name = app_name or module_app_name
        elif isinstance(target, _RouterUrls):
            entries = [target]
        elif isinstance(target, list):
            entries = self._entries(target, call)
        elif isinstance(target, _Included):
            return target
        else:
            reason = getattr(target, "reason", "unsupported argument")
            self.reader.unresolved(f"{self._at(call)}: include() could not be read ({reason})")
            entries = []
        ns = namespace if isinstance(namespace, str) else app_name
        return _Included(entries, ns if isinstance(ns, str) else None)

    def _i18n(self, call: ast.Call) -> Any:
        entries: list[Any] = []
        for argument in call.args:
            if isinstance(argument, ast.Starred):
                entries.extend(self._entries(self.evaluate(argument.value), argument))
            else:
                entries.extend(self._entries([self.evaluate(argument)], argument))
        if self._keyword(call, "prefix_default_language", 99) is False:
            return entries
        prefix = RoutePart(f"{self.reader.language_code}/")
        return [_Branch(prefix, _Included(entries), self._where(call))]

    # -- helpers ---------------------------------------------------------------
    def _entries(self, value: Any, node: ast.AST | None) -> list[Any]:
        """``value`` as a list of URL entries; reports what is not one."""
        if isinstance(value, _RouterUrls):
            return [value]
        if isinstance(value, _Included):
            return value.entries
        if not isinstance(value, (list, tuple)):
            reason = getattr(value, "reason", f"{type(value).__name__} is not a list")
            where = self._at(node, value)
            self.reader.unresolved(f"{where}: URL patterns could not be read ({reason})")
            return []
        entries = []
        for item in value:
            if isinstance(item, (_Leaf, _Branch, _RouterUrls)):
                entries.append(item)
            elif isinstance(item, list):
                entries.extend(self._entries(item, node))
            else:
                reason = getattr(item, "reason", f"{type(item).__name__} is not a URL pattern")
                where = self._at(node, item)
                self.reader.unresolved(f"{where}: an entry was skipped ({reason})")
        return entries

    def _keyword(self, call: ast.Call, name: str, position: int) -> Any:
        for keyword in call.keywords:
            if keyword.arg == name:
                return self.evaluate(keyword.value)
        if position < len(call.args):
            return self.evaluate(call.args[position])
        return None

    def _where(self, node: ast.AST) -> _Where:
        return _Where(self.source, getattr(node, "lineno", 0))

    def _at(self, node: ast.AST | None, value: Any = None) -> str:
        """``file:line`` of a value (where it was computed) or else of ``node``."""
        line = getattr(value, "line", 0) or getattr(node, "lineno", 0)
        return f"{self.source}:{line}"


def _admin_index(where: _Where) -> _Leaf:
    return _Leaf(RoutePart(""), "index", "admin.site.urls", where)


class UrlConfReader:
    """Follows ``include()`` across the project's URL modules."""

    def __init__(self, roots: list[Path], base: Path, language_code: str | None = None) -> None:
        self.finder = SettingsReader(roots, base)
        self.base = base
        self.language_code = (language_code or _DEFAULT_LANGUAGE).lower()
        self.problems: list[str] = []
        self._scopes: dict[str, dict[str, Any] | None] = {}
        self._loading: set[str] = set()

    def relative(self, path: Path) -> str:
        return self.finder.relative(path)

    def unresolved(self, message: str) -> None:
        if message not in self.problems:
            self.problems.append(message)

    def module_scope(self, module: str, depth: int = 0) -> dict[str, Any] | None:
        """Top-level values of a project module, ``None`` when it is not ours."""
        if module in self._scopes:
            return self._scopes[module]
        path = self.finder.find_module(module)
        if path is None or module in self._loading or depth > _MAX_DEPTH:
            return None
        self._loading.add(module)
        try:
            scope = _UrlModule(self, module, path, depth).run()
        finally:
            self._loading.discard(module)
        self._scopes[module] = scope
        return scope

    def include_module(
        self, module: str, call: ast.Call, caller: _UrlModule
    ) -> tuple[list[Any], str | None]:
        """``urlpatterns`` and ``app_name`` of an included module."""
        if module.split(".")[0] in _IGNORED_MODULES:
            return [], None
        builtin = _BUILTIN_URLCONFS.get(module)
        if builtin is not None:
            where = caller._where(call)
            return [_Leaf(RoutePart(route), name, module, where) for route, name in builtin], None
        scope = self.module_scope(module, caller.depth + 1)
        if scope is None:
            loop = module in self._loading
            what = "includes itself" if loop else "is not part of the project"
            self.unresolved(f"{caller._at(call)}: include({module!r}) {what}")
            return [], None
        return scope[_MODULE].urlpatterns() or ([], None)

    def read(self, module: str) -> UrlConf:
        conf = UrlConf(module=module)
        scope = self.module_scope(module)
        if scope is None:
            self.unresolved(f"ROOT_URLCONF {module!r} not found")
        else:
            entries, _ = scope[_MODULE].urlpatterns() or ([], None)
            conf.patterns = list(_flatten(entries, (), ()))
        conf.unresolved = list(self.problems)
        return conf


def _flatten(
    entries: list[Any], prefix: tuple[RoutePart, ...], namespaces: tuple[str, ...]
) -> Iterator[UrlPattern]:
    for entry in entries:
        if isinstance(entry, _Leaf):
            name = ":".join([*namespaces, entry.name]) if entry.name else None
            parts = tuple(p for p in (*prefix, entry.part) if p.text)
            yield UrlPattern(parts, name, entry.view, entry.where.source, entry.where.line)
        elif isinstance(entry, _Branch):
            ns = entry.included.namespace
            yield from _flatten(
                entry.included.entries,
                (*prefix, entry.part),
                (*namespaces, ns) if ns else namespaces,
            )
        elif isinstance(entry, _RouterUrls):
            yield from _flatten(_router_entries(entry.router), prefix, namespaces)


def _router_entries(router: _Router) -> list[_Leaf]:
    """The routes ``DefaultRouter`` / ``SimpleRouter`` generate (list and detail)."""
    slash = router.trailing_slash
    leaves = []
    if router.root_view and router.registered:
        where = router.registered[0][3]
        leaves.append(_Leaf(RoutePart("^$", regex=True), "api-root", "APIRootView", where))
    for prefix, view, basename, where in router.registered:
        base = prefix.strip("/")
        leaves.append(_Leaf(RoutePart(f"^{base}{slash}$", True), f"{basename}-list", view, where))
        detail = RoutePart(f"^{base}/(?P<pk>[^/.]+){slash}$", regex=True)
        leaves.append(_Leaf(detail, f"{basename}-detail", view, where))
    return leaves


def read_urlconf(
    module: str, roots: list[Path], base: Path, language_code: str | None = None
) -> UrlConf:
    """Read ``ROOT_URLCONF`` (e.g. ``config.urls``) found below one of ``roots``."""
    return UrlConfReader(roots, base, language_code).read(module)


def project_urlconf(project: Project) -> UrlConf | None:
    """The URLconf of a Django project, or ``None`` without ``ROOT_URLCONF``."""
    settings = project.settings
    module = settings.get("ROOT_URLCONF") if settings is not None else None
    if not isinstance(module, str) or not module:
        return None
    language = settings.get("LANGUAGE_CODE") if settings is not None else None
    return read_urlconf(
        module,
        module_roots(project.root),
        project.root,
        language if isinstance(language, str) else None,
    )
