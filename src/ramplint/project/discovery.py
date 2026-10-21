"""Find Django projects and the folders Django loads templates from."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any

from ramplint.project.settings import UNKNOWN, Settings, SettingsReader

#: Folders that never contain the project's own templates.
SKIP_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", ".tox", ".nox", ".venv", "venv", "env", "node_modules",
        "__pycache__", "build", "dist", "site-packages", ".mypy_cache", ".pytest_cache",
        ".ruff_cache", "htmlcov", "static", "staticfiles", "collected_static", "media",
    }
)  # fmt: skip

_SETTINGS_RE = re.compile(r"""DJANGO_SETTINGS_MODULE["']\s*,\s*["']([\w.]+)["']""")
#: Modules that commonly hold the real settings of a settings package.
_PACKAGE_DEFAULTS = ("base", "common", "defaults", "default", "settings")
_APP_MARKERS = ("apps.py", "models.py", "views.py", "__init__.py")


@dataclass(frozen=True)
class TemplateDir:
    path: Path
    #: Where it came from: ``DIRS``, ``app shop``, ``template-dirs``, ``fallback``.
    origin: str
    #: ``django`` or ``jinja2``.
    backend: str = "django"


@dataclass
class Project:
    root: Path
    settings_module: str | None = None
    #: How the settings module was found: ``--settings``, ``pyproject.toml``,
    #: ``environment``, ``manage.py``, ``wsgi.py``, ``asgi.py`` or ``guess``.
    settings_source: str | None = None
    template_dirs: list[TemplateDir] = field(default_factory=list)
    #: True when the folders come from TEMPLATES in the settings.
    from_settings: bool = False
    warnings: list[str] = field(default_factory=list)

    def relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix() or "."
        except ValueError:
            return path.as_posix()


def find_project_root(path: Path) -> Path | None:
    """The nearest folder at or above ``path`` that has a ``manage.py``."""
    path = path.resolve()
    directory = path if path.is_dir() else path.parent
    for candidate in (directory, *directory.parents):
        if (candidate / "manage.py").is_file():
            return candidate
    return None


def _module_roots(root: Path) -> list[Path]:
    roots = [root]
    if (root / "src").is_dir():
        roots.append(root / "src")
    return roots


def _settings_from_file(path: Path) -> str | None:
    try:
        match = _SETTINGS_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    return match.group(1) if match else None


def _entry_points(root: Path) -> Iterator[tuple[str, Path]]:
    yield "manage.py", root / "manage.py"
    for name in ("wsgi.py", "asgi.py"):
        for depth in ("*", "*/*", "src/*"):
            for path in sorted(root.glob(f"{depth}/{name}")):
                yield name, path
        yield name, root / name


def _guess_settings(root: Path) -> str | None:
    for module_root in _module_roots(root):
        if (module_root / "settings.py").is_file() or (module_root / "settings").is_dir():
            return "settings"
        for child in sorted(module_root.iterdir()):
            if not child.is_dir() or child.name in SKIP_DIRS or child.name.startswith("."):
                continue
            if (child / "settings.py").is_file() or (child / "settings" / "__init__.py").is_file():
                return f"{child.name}.settings"
    return None


def _flatten_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _flatten_strings(item)


def _uses_app_directories(backend: dict[str, Any]) -> bool:
    if backend.get("APP_DIRS") is True:
        return True
    options = backend.get("OPTIONS")
    if isinstance(options, dict):
        loaders = options.get("loaders")
        return any("app_directories" in loader for loader in _flatten_strings(loaders))
    return False


def _backend_kind(name: Any) -> str | None:
    if not isinstance(name, str):
        return None
    if "jinja2" in name.lower():
        return "jinja2"
    if name.endswith("DjangoTemplates"):
        return "django"
    return None


def _is_skipped(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True  # outside the project: an installed package
    return any(part in SKIP_DIRS or part.endswith(".egg-info") for part in parts)


def _app_folder(app: str, roots: list[Path]) -> Path | None:
    """``shop`` / ``apps.shop`` / ``shop.apps.ShopConfig`` -> the app package."""
    parts = app.split(".")
    for root in roots:
        for size in range(len(parts), 0, -1):
            candidate = root.joinpath(*parts[:size])
            if candidate.is_dir() and any((candidate / m).exists() for m in _APP_MARKERS):
                return candidate
    return None


class _Discovery:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.roots = _module_roots(root)
        self.warnings: list[str] = []
        self.dirs: list[TemplateDir] = []
        #: Some TEMPLATES entries could not be read statically.
        self.incomplete = False

    def _root_of(self, folder: Path) -> Path:
        roots = sorted(self.roots, key=lambda r: len(r.parts), reverse=True)
        return next((r for r in roots if folder.is_relative_to(r)), self.root)

    def add(self, path: Path, origin: str, backend: str) -> None:
        path = path.resolve()
        if not path.is_dir():
            return
        if any(existing.path == path for existing in self.dirs):
            return
        self.dirs.append(TemplateDir(path=path, origin=origin, backend=backend))

    def from_settings(self, settings: Settings) -> bool:
        templates = settings.get("TEMPLATES")
        if not isinstance(templates, (list, tuple)):
            return False
        apps = settings.get("INSTALLED_APPS")
        app_names: list[str] = []
        if isinstance(apps, (list, tuple)):
            for app in apps:
                if isinstance(app, str):
                    app_names.append(app)
                else:
                    self.warnings.append("an INSTALLED_APPS entry could not be read")
        elif apps is not None:
            self.warnings.append("INSTALLED_APPS could not be read")

        found_backend = False
        for backend in templates:
            if not isinstance(backend, dict):
                self.warnings.append("a TEMPLATES entry could not be read")
                self.incomplete = True
                continue
            kind = _backend_kind(backend.get("BACKEND"))
            if kind is None:
                if backend.get("BACKEND") is not UNKNOWN:
                    name = backend.get("BACKEND")
                    self.warnings.append(f"template backend {name!r} is not supported")
                continue
            found_backend = True
            dirs = backend.get("DIRS", [])
            for entry in dirs if isinstance(dirs, (list, tuple)) else [UNKNOWN]:
                if isinstance(entry, (str, PurePath)):
                    path = Path(entry)
                    self.add(path if path.is_absolute() else self.root / path, "DIRS", kind)
                else:
                    self.warnings.append(f"a {kind} DIRS entry could not be read")
                    self.incomplete = True
            if _uses_app_directories(backend):
                subfolder = "jinja2" if kind == "jinja2" else "templates"
                for app in app_names:
                    folder = _app_folder(app, self.roots)
                    if folder is None or _is_skipped(folder, self.root):
                        continue  # Django, third-party apps
                    label = ".".join(folder.relative_to(self._root_of(folder)).parts)
                    self.add(folder / subfolder, f"app {label}", kind)
        return found_backend

    def fallback(self) -> None:
        """Template folders next to apps, and the project-level folder."""
        for dirpath, dirnames, _ in os.walk(self.root):
            current = Path(dirpath)
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".") and not d.endswith(".egg-info")
            )  # fmt: skip
            for name in ("templates", "jinja2"):
                if name not in dirnames:
                    continue
                parent_is_app = any((current / marker).is_file() for marker in _APP_MARKERS)
                if parent_is_app or current == self.root or (current / "settings.py").exists():
                    backend = "jinja2" if name == "jinja2" else "django"
                    self.add(current / name, "fallback", backend)
            # Do not descend into template folders themselves.
            dirnames[:] = [d for d in dirnames if d not in ("templates", "jinja2")]


def discover_project(
    root: Path,
    settings_module: str | None = None,
    settings_source: str | None = None,
    environ: dict[str, str] | None = None,
) -> Project:
    """Read the settings of the project in ``root`` and find its template folders."""
    root = root.resolve()
    env = os.environ if environ is None else environ
    discovery = _Discovery(root)
    reader = SettingsReader(discovery.roots, base=root)

    candidates: list[tuple[str, str]] = []
    if settings_module:
        candidates.append((settings_module, settings_source or "--settings"))
    else:
        if env.get("DJANGO_SETTINGS_MODULE"):
            candidates.append((env["DJANGO_SETTINGS_MODULE"], "environment"))
        for source, path in _entry_points(root):
            module = _settings_from_file(path)
            if module:
                candidates.append((module, source))
        guess = _guess_settings(root)
        if guess:
            candidates.append((guess, "guess"))

    project = Project(root=root)
    for module, source in candidates:
        if reader.find_module(module) is None:
            if source in ("--settings", "pyproject.toml"):
                raise SettingsNotFound(module, root)
            continue
        settings = reader.read(module)
        if settings is not None and settings.get("TEMPLATES") is None:
            # A settings package whose __init__.py only picks a module.
            for name in _PACKAGE_DEFAULTS:
                fallback = reader.read(f"{module}.{name}")
                if fallback is not None and fallback.get("TEMPLATES") is not None:
                    module, settings = f"{module}.{name}", fallback
                    break
        project.settings_module, project.settings_source = module, source
        if settings is not None and discovery.from_settings(settings):
            project.from_settings = True
        break

    if not project.from_settings or discovery.incomplete:
        if project.settings_module and not project.from_settings:
            discovery.warnings.append(
                f"no TEMPLATES found in {project.settings_module}; looking for template folders"
            )
        discovery.fallback()
    project.template_dirs = discovery.dirs
    project.warnings = [*reader.warnings, *discovery.warnings]
    return project


def configured_project(root: Path, template_dirs: Iterable[str]) -> Project:
    """A project whose template folders are set in ``[tool.ramplint] template-dirs``."""
    root = root.resolve()
    project = Project(root=root, settings_source="pyproject.toml")
    for entry in template_dirs:
        path = (root / entry).resolve()
        if path.is_dir():
            project.template_dirs.append(TemplateDir(path=path, origin="template-dirs"))
        else:
            project.warnings.append(f"template folder {entry} does not exist")
    project.from_settings = True
    return project


class SettingsNotFound(Exception):
    def __init__(self, module: str, root: Path) -> None:
        super().__init__(f"settings module {module!r} not found in {root}")
        self.module = module
