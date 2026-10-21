"""Read settings from ``[tool.ramplint]`` in ``pyproject.toml``."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python < 3.11 only
    import tomli as tomllib


class ConfigError(Exception):
    pass


@dataclass
class Config:
    select: list[str] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)
    #: Find Django projects and their template folders.
    django: bool = True
    django_settings: str | None = None
    template_dirs: list[str] = field(default_factory=list)
    source: Path | None = None


_LIST_KEYS = ("select", "ignore", "exclude", "extensions", "template-dirs")


def find_pyproject(start: Path) -> Path | None:
    start = start.resolve()
    for directory in (start, *start.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def load_config(path: Path | None = None, start: Path | None = None) -> Config:
    """Load config from ``path`` or the nearest ``pyproject.toml``."""
    if path is None:
        path = find_pyproject(start or Path.cwd())
        if path is None:
            return Config()
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc

    section = data.get("tool", {}).get("ramplint", {})
    config = Config(source=path)
    for key, value in section.items():
        normalized = key.replace("_", "-")
        if normalized == "django":
            if not isinstance(value, bool):
                raise ConfigError(f"{path}: [tool.ramplint].{key} must be true or false")
            config.django = value
        elif normalized == "django-settings":
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"{path}: [tool.ramplint].{key} must be a module name")
            config.django_settings = value.strip()
        elif normalized in _LIST_KEYS:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(f"{path}: [tool.ramplint].{key} must be a list of strings")
            setattr(config, normalized.replace("-", "_"), list(value))
        else:
            raise ConfigError(f"{path}: unknown option [tool.ramplint].{key}")
    return config
