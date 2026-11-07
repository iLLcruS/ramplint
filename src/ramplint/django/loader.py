"""``SourceMapLoader``: adds ``data-rl-src`` to templates while ``DEBUG`` is on."""

from __future__ import annotations

import copy
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from django.conf import settings
from django.template import Origin
from django.template.loaders.base import Loader

from ramplint.sourcemap import annotate

_DJANGO_BACKEND = "django.template.backends.django.DjangoTemplates"
_DEFAULT_LOADERS = ["django.template.loaders.filesystem.Loader"]
_APP_LOADER = "django.template.loaders.app_directories.Loader"


class SourceMapLoader(Loader):
    """Wraps other loaders; their templates get ``data-rl-src`` on every element.

    Does nothing unless ``DEBUG`` is on, so it can never leak into production.
    """

    def __init__(self, engine: Any, loaders: list[Any]) -> None:
        super().__init__(engine)
        self.loaders = engine.get_template_loaders(loaders)
        root = getattr(settings, "RAMPLINT_SOURCE_ROOT", None) or os.getcwd()
        self.root = Path(root).resolve()

    def get_template_sources(self, template_name: str) -> Iterator[Origin]:
        for loader in self.loaders:
            yield from loader.get_template_sources(template_name)

    def get_contents(self, origin: Origin) -> str:
        contents = origin.loader.get_contents(origin)
        path = self._project_path(origin.name)
        if not settings.DEBUG or path is None:
            return contents
        return annotate(contents, path)

    def _project_path(self, name: str) -> str | None:
        """The template's path in the project; ``None`` for installed packages
        (Django's own widget templates): their problems are reported by URL."""
        path = Path(name).resolve()
        if "site-packages" in path.parts or "dist-packages" in path.parts:
            return None
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return None

    def reset(self) -> None:
        for loader in self.loaders:
            if hasattr(loader, "reset"):
                loader.reset()


def wrap_template_loaders(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A copy of ``TEMPLATES`` whose Django backends load through ``SourceMapLoader``."""
    result = copy.deepcopy(templates)
    for backend in result:
        if backend.get("BACKEND") != _DJANGO_BACKEND:
            continue  # Jinja2: findings fall back to URL and selector
        options = backend.setdefault("OPTIONS", {})
        loaders = options.get("loaders")
        if loaders is None:
            loaders = list(_DEFAULT_LOADERS)
            if backend.get("APP_DIRS"):
                loaders.append(_APP_LOADER)
        backend["APP_DIRS"] = False  # Django refuses APP_DIRS together with loaders
        options["loaders"] = [("ramplint.django.SourceMapLoader", loaders)]
    return result
