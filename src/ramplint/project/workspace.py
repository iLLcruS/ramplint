"""Choose which files to lint and give each one its cross-template context."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from ramplint.project.context import TemplateContext
from ramplint.project.discovery import (
    SKIP_DIRS,
    Project,
    configured_project,
    discover_project,
    find_project_root,
)
from ramplint.project.templates import TemplateIndex
from ramplint.pyforms import is_forms_module

#: Folder names that hold templates when there is no Django project to ask.
TEMPLATE_FOLDER_NAMES = ("templates", "jinja2")


class Workspace:
    def __init__(
        self,
        extensions: Iterable[str],
        exclude: Iterable[str] = (),
        skip_dirs: Iterable[str] = (),
        django: bool = True,
        settings: str | None = None,
        settings_source: str | None = None,
        template_dirs: list[str] | None = None,
        config_root: Path | None = None,
        cwd: Path | None = None,
        environ: dict[str, str] | None = None,
        forms: bool = True,
    ) -> None:
        #: Also lint Django forms modules (``forms.py``).
        self.forms = forms
        self.extensions = tuple(
            e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions
        )
        self.exclude = list(exclude)
        self.skip_dirs = frozenset(skip_dirs)
        self.django = django
        self.settings = settings
        self.settings_source = settings_source
        self.cwd = (cwd or Path.cwd()).resolve()
        self.environ = environ
        self.configured: Project | None = None
        if template_dirs:
            self.configured = configured_project(config_root or self.cwd, template_dirs)
        self.projects: dict[Path, Project] = {}
        self._indexes: dict[tuple[Path, ...], TemplateIndex] = {}

    # -- projects ----------------------------------------------------------
    def project(self, root: Path) -> Project:
        root = root.resolve()
        if root not in self.projects:
            self.projects[root] = discover_project(
                root, self.settings, self.settings_source, self.environ
            )
        return self.projects[root]

    def project_for(self, path: Path) -> Project | None:
        if self.configured is not None:
            return self.configured
        if not self.django:
            return None
        root = find_project_root(path)
        return self.project(root) if root is not None else None

    # -- files -------------------------------------------------------------
    def _display(self, path: Path) -> Path:
        try:
            return path.resolve().relative_to(self.cwd)
        except ValueError:
            return path

    def _excluded(self, path: Path) -> bool:
        posix = self._display(path).as_posix()
        return any(
            fnmatch.fnmatch(posix, pattern) or fnmatch.fnmatch(path.name, pattern)
            for pattern in self.exclude
        )

    def _walk(self, root: Path, swap_projects: bool) -> Iterator[Path]:
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            if swap_projects and current != root and (current / "manage.py").is_file():
                dirnames[:] = []
                yield from self._project_files(self.project(current), current)
                continue
            dirnames[:] = sorted(
                d
                for d in dirnames
                if d not in self.skip_dirs
                and not d.endswith(".egg-info")
                and not self._excluded(current / d)
            )
            for filename in sorted(filenames):
                path = current / filename
                if filename.lower().endswith(self.extensions) or (
                    self.forms and is_forms_module(path)
                ):
                    yield path

    def _project_files(self, project: Project, root: Path) -> Iterator[Path]:
        no_settings = not project.from_settings and project.settings_module is None
        if not project.template_dirs and no_settings:
            yield from self._walk(root, swap_projects=False)  # nothing to go on
            return
        for template_dir in project.template_dirs:
            yield from self._walk(template_dir.path, swap_projects=False)
        if self.forms:
            yield from self._forms_modules(project.root)

    def _forms_modules(self, root: Path) -> Iterator[Path]:
        """``forms.py`` files and ``forms/`` packages of the project's own code."""
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            dirnames[:] = sorted(
                d
                for d in dirnames
                if d not in self.skip_dirs
                and d not in SKIP_DIRS
                and not d.startswith(".")
                and not d.endswith(".egg-info")
                and not self._excluded(current / d)
            )
            for filename in sorted(filenames):
                if is_forms_module(current / filename):
                    yield current / filename

    def files(self, paths: list[str] | None) -> Iterator[Path]:
        """Template files to lint. Explicit files are always included."""
        seen: set[Path] = set()
        for path in self._candidates(paths):
            resolved = path.resolve()
            if resolved in seen or self._excluded(path):
                continue
            seen.add(resolved)
            yield self._display(path)

    def _candidates(self, paths: list[str] | None) -> Iterator[Path]:
        if not paths:
            if self.configured is not None:
                yield from self._project_files(self.configured, self.cwd)
                return
            root = find_project_root(self.cwd) if self.django else None
            if root is not None and root == self.cwd:
                yield from self._project_files(self.project(root), root)
            else:
                # Below a project root, or no project above: walk the folder,
                # switching to discovery for projects found inside it.
                yield from self._walk(self.cwd, swap_projects=self.django and root is None)
            return
        for raw in paths:
            path = Path(raw)
            if not path.is_absolute() and Path.cwd().resolve() != self.cwd:
                path = self.cwd / path
            if path.is_file():
                yield path
            elif not path.is_dir():
                raise FileNotFoundError(raw)
            elif self.django and (path / "manage.py").is_file():
                yield from self._project_files(self.project(path), path)
            else:
                yield from self._walk(path, swap_projects=self.django)

    # -- context -----------------------------------------------------------
    def _index(self, dirs: list[Path]) -> TemplateIndex:
        key = tuple(dirs)
        if key not in self._indexes:
            self._indexes[key] = TemplateIndex(dirs, self.extensions)
        return self._indexes[key]

    def index_for(self, path: Path) -> TemplateIndex | None:
        path = path.resolve()
        project = self.project_for(path)
        if project is not None and project.template_dirs:
            dirs = [d.path for d in project.template_dirs]
            if any(path.is_relative_to(d) for d in dirs):
                return self._index(dirs)
        # No project: the nearest folder called "templates" or "jinja2".
        for parent in path.parents:
            if parent.name in TEMPLATE_FOLDER_NAMES:
                return self._index([parent])
        return None

    def python_index(self, path: Path) -> TemplateIndex | None:
        """Templates of the project a Python module belongs to (for widget templates)."""
        project = self.project_for(path.resolve())
        if project is None or not project.template_dirs:
            return None
        return self._index([d.path for d in project.template_dirs])

    def context_for(self, path: Path) -> TemplateContext | None:
        index = self.index_for(path)
        if index is None:
            return None
        template = index.load(path)
        return TemplateContext(template, index) if template is not None else None
