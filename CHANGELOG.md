# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `-o` / `--output FILE` writes the report to a file and prints a one-line
  summary (#8).
- `--format html`: a self-contained HTML report with a summary, problems by
  rule and problems grouped by template; light and dark themes (#9).
- HTML report shows the template lines around each problem, links rules to
  their documentation and can be filtered by rule and template (#10).
- `--format sarif`: SARIF 2.1.0 output for GitHub Code Scanning, with a
  ready-to-copy workflow in the README (#11).
- `--statistics` shows the number of problems per rule, most frequent first,
  as text or JSON (#12).

### Changed

- Output formats live in a small registry, so a new format is a single
  decorated function (#8).

## [0.2.1] - 2026-10-21

### Fixed

- Images and links in the project description on PyPI (the README used
  relative paths that only work on GitHub).
- `ramplint ... | head` no longer prints a `BrokenPipeError` traceback.

## [0.2.0] - 2026-10-21

### Added

- `RL102` iframe-title: `<iframe>` and `<frame>` elements must have a title (#1).
- `RL303` duplicate-id: `id` values must be unique; the same id in mutually
  exclusive `{% if %}` / `{% else %}` branches is allowed (#2).
- `RL503` no-positive-tabindex: `tabindex` greater than 0 is reported (#3).
- `RL602` viewport-zoom: `user-scalable=no` and `maximum-scale` below 2 in the
  viewport meta tag are reported (#4).
- `RL504` anchor-is-valid: `<a href="#">`, `javascript:` links and `<a>` with a
  click handler but no `href` are reported; use `<button>` for actions (#5).
- `RL402` autocomplete-valid: `autocomplete` values are checked against the HTML
  autofill grammar, with "did you mean" suggestions for typos (#6).

### Changed

- ramplint now knows which `{% if %}` / `{% else %}` / `{% for %}` / `{% empty %}`
  branch an element is rendered in.
- Attribute values built with template tags (for example
  `class="{% if active %}on{% endif %}"`) are treated as dynamic by every rule.
- README examples and sample output are verified by the test suite.

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

[Unreleased]: https://github.com/iLLcruS/ramplint/compare/0.2.1...HEAD
[0.2.1]: https://github.com/iLLcruS/ramplint/compare/0.2.0...0.2.1
[0.2.0]: https://github.com/iLLcruS/ramplint/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/iLLcruS/ramplint/releases/tag/0.1.0
