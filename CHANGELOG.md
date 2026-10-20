# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-20

### Added

- Template-aware parsing for Django and Jinja2 (`{{ }}`, `{% %}`, `{# #}`,
  `{% comment %}`) with exact line/column positions.
- Rules: `RL101` img-alt, `RL201` table-header, `RL301` heading-order,
  `RL302` empty-heading, `RL401` form-label, `RL501` button-name,
  `RL502` link-name, `RL601` html-lang.
- Inline suppressions: `{# ramplint: ignore RL101 #}` and
  `{# ramplint: ignore-file #}`.
- `text`, `json` and `github` output formats.
- Configuration via `[tool.ramplint]` in `pyproject.toml`.
- pre-commit hook.

[Unreleased]: https://github.com/iLLcruS/ramplint/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/iLLcruS/ramplint/releases/tag/v0.1.0
