"""Read Django settings without importing them.

Settings modules are evaluated with a tiny interpreter over the ``ast``: only
assignments, imports from other project modules and the handful of
expressions that settings use to build paths and lists. Anything else
(``env("...")``, function calls, database URLs) becomes :data:`UNKNOWN`, so
reading settings never runs project code, needs no database and has no side
effects.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any


class _Unknown:
    """A value that cannot be computed statically."""

    _instance: _Unknown | None = None

    def __new__(cls) -> _Unknown:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __bool__(self) -> bool:
        return False


UNKNOWN: Any = _Unknown()

#: Settings modules can be large; nothing we need is computed in a loop.
_MAX_MODULE_DEPTH = 20


@dataclass
class Settings:
    """The values read from a settings module and everything it imports."""

    module: str
    values: dict[str, Any] = field(default_factory=dict)
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def get(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)


class _Function:
    """A ``lambda`` or a ``def`` whose body is a single ``return``."""

    def __init__(self, params: list[str], body: ast.expr, scope: dict[str, Any], interp: _Module):
        self.params = params
        self.body = body
        self.scope = scope
        self.interp = interp

    def __call__(self, *args: Any) -> Any:
        if len(args) != len(self.params):
            return UNKNOWN
        local = dict(self.scope)
        local.update(zip(self.params, args, strict=True))
        return self.interp.evaluate(self.body, local)


def _os_path_join(*parts: Any) -> Any:
    if not parts or not all(isinstance(p, (str, PurePath)) for p in parts):
        return UNKNOWN
    return os.path.join(*(str(p) for p in parts))


def _str_path_function(function: Callable[[str], str]) -> Callable[[Any], Any]:
    def wrapper(value: Any) -> Any:
        if not isinstance(value, (str, PurePath)):
            return UNKNOWN
        return function(str(value))

    return wrapper


def _path(*parts: Any) -> Any:
    if not all(isinstance(p, (str, PurePath)) for p in parts):
        return UNKNOWN
    return Path(*parts)


def _str(value: Any = "") -> Any:
    if isinstance(value, (str, PurePath, int, float, bool)):
        return str(value)
    return UNKNOWN


_OS_PATH = {
    "join": _os_path_join,
    "dirname": _str_path_function(os.path.dirname),
    "abspath": _str_path_function(os.path.abspath),
    "realpath": _str_path_function(os.path.abspath),
    "normpath": _str_path_function(os.path.normpath),
    "basename": _str_path_function(os.path.basename),
    "expanduser": _str_path_function(lambda value: value),
}
#: Names importable from the standard library that settings use for paths.
_KNOWN_MODULES: dict[str, dict[str, Any]] = {
    "os": {"path": _OS_PATH},
    "os.path": _OS_PATH,
    "pathlib": {"Path": _path, "PurePath": _path},
}
_BUILTINS: dict[str, Any] = {
    "str": _str,
    "list": lambda value=(): list(value) if isinstance(value, (list, tuple)) else UNKNOWN,
    "tuple": lambda value=(): tuple(value) if isinstance(value, (list, tuple)) else UNKNOWN,
    "True": True,
    "False": False,
    "None": None,
}
_PATH_METHODS = {"resolve", "absolute", "expanduser"}
_LIST_MUTATORS = {"append", "extend", "insert"}


class _Module:
    """Evaluates one settings module."""

    def __init__(self, reader: SettingsReader, name: str, path: Path, depth: int) -> None:
        self.reader = reader
        self.name = name
        self.path = path
        self.depth = depth
        self.scope: dict[str, Any] = {"__file__": str(path), **_BUILTINS}

    # -- statements --------------------------------------------------------
    def run(self) -> dict[str, Any]:
        try:
            tree = ast.parse(self.path.read_text(encoding="utf-8"), filename=str(self.path))
        except (OSError, SyntaxError, ValueError) as exc:
            self.reader.warn(f"{self._where()}: cannot parse ({exc.__class__.__name__})")
            return self.scope
        self._run_body(tree.body)
        return self.scope

    def _run_body(self, body: list[ast.stmt]) -> None:
        for statement in body:
            self._run(statement)

    def _run(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Assign):
            value = self.evaluate(node.value, self.scope)
            for target in node.targets:
                self._assign(target, value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            self._assign(node.target, self.evaluate(node.value, self.scope))
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            current = self.scope.get(node.target.id, UNKNOWN)
            value = self.evaluate(node.value, self.scope)
            self.scope[node.target.id] = _binary(node.op, current, value)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            self._import(node)
        elif isinstance(node, ast.If):
            test = self.evaluate(node.test, self.scope)
            if test is UNKNOWN:
                # Most settings branch on DEBUG or the environment; the body
                # usually only adds apps, which is the safe direction.
                self._run_body(node.body)
            elif test:
                self._run_body(node.body)
            else:
                self._run_body(node.orelse)
        elif isinstance(node, ast.Try):
            self._run_body(node.body)
            self._run_body(node.orelse)
            self._run_body(node.finalbody)
        elif isinstance(node, ast.With):
            self._run_body(node.body)
        elif isinstance(node, ast.FunctionDef):
            self._define_function(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            self._mutate(node.value)

    def _assign(self, target: ast.expr, value: Any) -> None:
        if isinstance(target, ast.Name):
            self.scope[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            items = value if isinstance(value, (list, tuple)) else None
            for index, element in enumerate(target.elts):
                if items is not None and len(items) == len(target.elts):
                    self._assign(element, items[index])
                else:
                    self._assign(element, UNKNOWN)
        elif isinstance(target, ast.Subscript):
            container = self.evaluate(target.value, self.scope)
            key = self.evaluate(target.slice, self.scope)
            if isinstance(container, dict) and key is not UNKNOWN:
                container[key] = value

    def _define_function(self, node: ast.FunctionDef) -> None:
        body = [s for s in node.body if not _is_docstring(s)]
        if len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is not None:
            params = [arg.arg for arg in node.args.args]
            self.scope[node.name] = _Function(params, body[0].value, self.scope, self)
        else:
            self.scope[node.name] = UNKNOWN

    def _mutate(self, call: ast.Call) -> None:
        """``INSTALLED_APPS.append("x")`` and friends."""
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr in _LIST_MUTATORS):
            return
        target = self.evaluate(func.value, self.scope)
        if not isinstance(target, list):
            return
        args = [self.evaluate(arg, self.scope) for arg in call.args]
        if func.attr == "append" and len(args) == 1:
            target.append(args[0])
        elif func.attr == "extend" and len(args) == 1:
            if isinstance(args[0], (list, tuple)):
                target.extend(args[0])
            else:
                target.append(UNKNOWN)
        elif func.attr == "insert" and len(args) == 2 and isinstance(args[0], int):
            target.insert(args[0], args[1])

    def _import(self, node: ast.Import | ast.ImportFrom) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                known = _KNOWN_MODULES.get(alias.name)
                bound = alias.asname or alias.name.split(".")[0]
                if alias.asname is None and alias.name == "os.path":
                    self.scope["os"] = _KNOWN_MODULES["os"]
                else:
                    self.scope[bound] = known if known is not None else UNKNOWN
            return

        module = self._absolute(node.module or "", node.level)
        if module in _KNOWN_MODULES:
            names = _KNOWN_MODULES[module]
            for alias in node.names:
                self.scope[alias.asname or alias.name] = names.get(alias.name, UNKNOWN)
            return
        values = self.reader.module_values(module, self.depth + 1)
        for alias in node.names:
            if alias.name == "*":
                if values is not None:
                    self.scope.update({k: v for k, v in values.items() if not k.startswith("_")})
                continue
            bound = alias.asname or alias.name
            if values is not None and alias.name in values:
                self.scope[bound] = values[alias.name]
            else:
                self.scope[bound] = UNKNOWN

    def _absolute(self, module: str, level: int) -> str:
        if level == 0:
            return module
        package = self.name.split(".")
        if self.path.name != "__init__.py":
            package = package[:-1]
        if level > 1:
            package = package[: len(package) - (level - 1)]
        return ".".join([*package, module] if module else package)

    def _where(self) -> str:
        return self.reader.relative(self.path)

    # -- expressions -------------------------------------------------------
    def evaluate(self, node: ast.expr, scope: dict[str, Any]) -> Any:
        try:
            return self._evaluate(node, scope)
        except (TypeError, ValueError, KeyError, IndexError, AttributeError, RecursionError):
            return UNKNOWN

    def _evaluate(self, node: ast.expr, scope: dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return scope.get(node.id, UNKNOWN)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            items: list[Any] = []
            for element in node.elts:
                if isinstance(element, ast.Starred):
                    value = self._evaluate(element.value, scope)
                    if isinstance(value, (list, tuple)):
                        items.extend(value)
                    else:
                        items.append(UNKNOWN)
                else:
                    items.append(self._evaluate(element, scope))
            return tuple(items) if isinstance(node, ast.Tuple) else items
        if isinstance(node, ast.Dict):
            result: dict[Any, Any] = {}
            for key, value in zip(node.keys, node.values, strict=True):
                if key is None:  # {**other}
                    other = self._evaluate(value, scope)
                    if isinstance(other, dict):
                        result.update(other)
                    continue
                result[self._evaluate(key, scope)] = self._evaluate(value, scope)
            return result
        if isinstance(node, ast.BinOp):
            return _binary(
                node.op, self._evaluate(node.left, scope), self._evaluate(node.right, scope)
            )
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                part = (
                    value.value
                    if isinstance(value, ast.Constant)
                    else self._evaluate(value.value, scope)  # type: ignore[attr-defined]
                )
                if not isinstance(part, (str, int, PurePath)):
                    return UNKNOWN
                parts.append(str(part))
            return "".join(parts)
        if isinstance(node, ast.Attribute):
            return _attribute(self._evaluate(node.value, scope), node.attr)
        if isinstance(node, ast.Subscript):
            container = self._evaluate(node.value, scope)
            key = self._evaluate(node.slice, scope)
            if container is UNKNOWN or key is UNKNOWN:
                return UNKNOWN
            if isinstance(container, (list, tuple, dict)) or isinstance(key, int):
                return container[key]
            return UNKNOWN
        if isinstance(node, ast.Call):
            return self._call(node, scope)
        if isinstance(node, ast.Lambda):
            params = [arg.arg for arg in node.args.args]
            return _Function(params, node.body, scope, self)
        if isinstance(node, ast.IfExp):
            test = self._evaluate(node.test, scope)
            if test is UNKNOWN:
                return UNKNOWN
            return self._evaluate(node.body if test else node.orelse, scope)
        return UNKNOWN

    def _call(self, node: ast.Call, scope: dict[str, Any]) -> Any:
        func = node.func
        args = [self._evaluate(arg, scope) for arg in node.args]
        if isinstance(func, ast.Attribute):
            owner = self._evaluate(func.value, scope)
            if isinstance(owner, PurePath):
                if func.attr in _PATH_METHODS:
                    return owner
                if func.attr == "joinpath" and all(isinstance(a, (str, PurePath)) for a in args):
                    return owner.joinpath(*args)
                return UNKNOWN
            if isinstance(owner, str) and func.attr == "format":
                return UNKNOWN
        callee = self._evaluate(func, scope)
        if callable(callee) and not isinstance(callee, _Unknown):
            return callee(*args)
        return UNKNOWN


def _is_docstring(statement: ast.stmt) -> bool:
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)


def _attribute(owner: Any, name: str) -> Any:
    if isinstance(owner, dict):
        return owner.get(name, UNKNOWN)
    if isinstance(owner, PurePath):
        if name == "parent":
            return owner.parent
        if name == "parents":
            return list(owner.parents)
        if name == "name":
            return owner.name
    return UNKNOWN


def _binary(op: ast.operator, left: Any, right: Any) -> Any:
    if left is UNKNOWN or right is UNKNOWN:
        if isinstance(op, ast.Add) and isinstance(left, list):
            return [*left, UNKNOWN]
        return UNKNOWN
    if isinstance(op, ast.Div) and isinstance(left, PurePath):
        if isinstance(right, (str, PurePath)):
            return left / right
        return UNKNOWN
    if isinstance(op, ast.Add):
        if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
            return [*left, *right] if isinstance(left, list) else (*left, *right)
        if isinstance(left, str) and isinstance(right, str):
            return left + right
    return UNKNOWN


class SettingsReader:
    """Finds and evaluates settings modules below ``roots``."""

    def __init__(self, roots: list[Path], base: Path | None = None) -> None:
        self.roots = roots
        self.base = base or (roots[0] if roots else Path.cwd())
        self._cache: dict[str, dict[str, Any] | None] = {}
        self._loading: set[str] = set()
        self.files: list[Path] = []
        self.warnings: list[str] = []

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.base).as_posix()
        except ValueError:
            return path.as_posix()

    def find_module(self, module: str) -> Path | None:
        """The file of a project module (``config.settings.base``)."""
        if not module:
            return None
        parts = module.split(".")
        for root in self.roots:
            candidate = root.joinpath(*parts)
            if candidate.with_suffix(".py").is_file():
                return candidate.with_suffix(".py")
            if (candidate / "__init__.py").is_file():
                return candidate / "__init__.py"
        return None

    def module_values(self, module: str, depth: int = 0) -> dict[str, Any] | None:
        """Top-level values of a project module, or None if it is not ours."""
        if module in self._cache:
            return self._cache[module]
        path = self.find_module(module)
        if path is None or module in self._loading or depth > _MAX_MODULE_DEPTH:
            return None
        self._loading.add(module)
        try:
            values = _Module(self, module, path, depth).run()
        finally:
            self._loading.discard(module)
        self._cache[module] = values
        if path not in self.files:
            self.files.append(path)
        return values

    def read(self, module: str) -> Settings | None:
        values = self.module_values(module)
        if values is None:
            return None
        public = {k: v for k, v in values.items() if k.isupper()}
        return Settings(
            module=module, values=public, files=list(self.files), warnings=self.warnings
        )


def read_settings(module: str, roots: list[Path], base: Path | None = None) -> Settings | None:
    """Evaluate ``module`` (``config.settings``) found below one of ``roots``."""
    return SettingsReader(roots, base).read(module)
