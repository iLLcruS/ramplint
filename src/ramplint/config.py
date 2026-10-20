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
    source: Path | None = None


_LIST_KEYS = ("select", "ignore", "exclude", "extensions")


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
        if normalized not in _LIST_KEYS:
            raise ConfigError(f"{path}: unknown option [tool.ramplint].{key}")
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"{path}: [tool.ramplint].{key} must be a list of strings")
        setattr(config, normalized, list(value))
    return config
