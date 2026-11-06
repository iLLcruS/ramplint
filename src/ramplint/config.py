"""Read settings from ``[tool.ramplint]`` in ``pyproject.toml``."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    #: ``[tool.ramplint.browser]``, validated, keys with underscores.
    browser: dict[str, Any] = field(default_factory=dict)
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
        elif normalized == "browser":
            config.browser = _browser_section(path, value)
        elif normalized in _LIST_KEYS:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(f"{path}: [tool.ramplint].{key} must be a list of strings")
            setattr(config, normalized.replace("-", "_"), list(value))
        else:
            raise ConfigError(f"{path}: unknown option [tool.ramplint].{key}")
    return config


def _browser_section(path: Path, section: object) -> dict[str, Any]:
    """Validate ``[tool.ramplint.browser]``."""
    from ramplint.browser.options import DEFAULT_DENY, is_url, parse_viewport

    where = f"{path}: [tool.ramplint.browser]"
    if not isinstance(section, dict):
        raise ConfigError(f"{where} must be a table")
    result: dict[str, Any] = {}
    for key, value in section.items():
        normalized = key.replace("_", "-")
        if normalized == "viewports":
            strings = isinstance(value, list) and all(isinstance(v, str) for v in value)
            if not value or not strings:
                raise ConfigError(f"{where}.{key} must be a non-empty list of strings")
            try:
                result["viewports"] = [parse_viewport(v) for v in value]
            except ValueError as exc:
                raise ConfigError(f"{where}.{key}: {exc}") from None
        elif normalized == "timeout":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ConfigError(f"{where}.{key} must be a number of seconds above 0")
            result["timeout"] = float(value)
        elif normalized == "delay":
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ConfigError(f"{where}.{key} must be a number of milliseconds")
            result["delay"] = value
        elif normalized == "headed":
            if not isinstance(value, bool):
                raise ConfigError(f"{where}.{key} must be true or false")
            result["headed"] = value
        elif normalized == "wait-for":
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"{where}.{key} must be a CSS selector")
            result["wait_for"] = value.strip()
        elif normalized == "base-url":
            if not isinstance(value, str) or not is_url(value.strip()):
                raise ConfigError(f"{where}.{key} must be an http:// or https:// URL")
            result["base_url"] = value.strip()
        elif normalized in ("max-pages", "per-pattern"):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ConfigError(f"{where}.{key} must be a whole number above 0")
            result[normalized.replace("-", "_")] = value
        elif normalized == "crawl":
            if not isinstance(value, bool):
                raise ConfigError(f"{where}.{key} must be true or false")
            result["crawl"] = value
        elif normalized in ("include", "exclude", "deny"):
            if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
                raise ConfigError(f"{where}.{key} must be a list of URL patterns")
            result[normalized] = [*DEFAULT_DENY, *value] if normalized == "deny" else value
        else:
            raise ConfigError(f"{where}: unknown option {key}")
    return result
