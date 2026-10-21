# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.5.0] - 2026-10-21

### Added

- Django project discovery: in a folder with `manage.py`, `ramplint` reads the
  settings module (from `--settings`, `DJANGO_SETTINGS_MODULE`, `manage.py`,
  `wsgi.py` / `asgi.py`, or a `settings.py` / `settings/` package) and lints the
  folders Django loads templates from: `TEMPLATES[...]["DIRS"]` and the
  `templates/` / `jinja2/` folders of the project's own apps. Settings are read
  with `ast`, never imported (#65).
- Supported layouts: `startproject`, settings packages with
  `from .base import *`, cookiecutter-django, `src/` layouts, apps in a
  subfolder, Jinja2, and monorepos with several `manage.py`. Without usable
  settings, template folders next to `apps.py` / `models.py` are used (#66).
- `--list-templates` (text or JSON) shows the project, the settings module and
  how it was found, the template folders with their origin, templates that
  override each other, and settings that could not be read (#67).
- `--settings`, `--no-django`, `--verbose`, and the `[tool.ramplint]` options
  `django-settings`, `template-dirs` and `django` (#68).
- `{% extends %}` and `{% include %}` are resolved to files the way Django's
  loaders do (#69):
  - `RL301` heading-order compares a child template's first heading in a block
    with the heading the parent renders before that block (#70).
  - `RL603` document-title reports pages whose
    `<title>{% block title %}{% endblock %}</title>` stays empty (#70).
  - `RL306` landmark-one-main reports a `<main>` inside a block that the parent
    already wraps in `<main>` (#70).
  - `RL403` label-for-target and `RL703` aria-valid-attr-value look for ids in
    included templates and in the templates a page extends (#71).
- `RL507` focusable-role: elements with an interactive role that cannot get
  keyboard focus (#72).
- `examples/django_project/`: a demo project with a settings package, two
  apps, a Jinja2 folder and a `static/` folder that is skipped (#73).

### Changed

- `ramplint` without arguments in a Django project lints the template folders
  from the settings instead of every template under the current folder. Folders
  passed explicitly are walked as before, but Django projects inside them (a
  folder with `manage.py`) are linted through their settings.
- In a child template, headings outside `{% block %}` (which Django never
  renders) are no longer checked by `RL301`, and headings in different blocks
  are no longer compared with each other.
- Without a resolvable parent template, `RL403` and `RL703` no longer check ids
  in child templates: the id may be in the parent.

## [0.4.1] - 2026-10-21

### Fixed

- `RL305` definition-list now reports a `<dd>` without a `<dt>` before it, a
  `<dt>` without a `<dd>` after it (also inside `<div>` groups) and empty
  `<dt>` elements.
- `RL402` autocomplete-valid no longer suggests unrelated tokens
  (`accountname` → `country-name`). Common non-standard names get the right
  token: `accountname` → `username`, `zip` → `postal-code`, `phone` → `tel`,
  `first_name` → `given-name`.

## [0.4.0] - 2026-10-21

### Added

- 21 new rules: ramplint now checks 35 rules (up from 14).
- WAI-ARIA rules:
  - `RL701` aria-role: unknown and abstract roles, with "did you mean" suggestions (#38).
  - `RL702` aria-valid-attr: misspelled `aria-*` attributes (#39).
  - `RL703` aria-valid-attr-value: invalid values and `aria-labelledby` /
    `aria-describedby` that reference missing ids (#40).
  - `RL704` aria-required-attr: roles without the states they require (#41).
  - `RL705` aria-hidden-focus: focusable content inside `aria-hidden="true"` (#42).
- Structure rules:
  - `RL304` list-structure: `<ul>` / `<ol>` with children other than `<li>`, and
    `<li>` outside a list; top-level `<li>` in partials is allowed (#43).
  - `RL305` definition-list: `<dl>` with children other than `<dt>`, `<dd>` and
    `<div>` groups, and `<dt>` / `<dd>` outside a `<dl>` (#44).
  - `RL505` nested-interactive: links, buttons, form controls and focusable
    elements inside `<a href>` or `<button>` (#45).
  - `RL202` th-scope: invalid `scope` values, with "did you mean" suggestions,
    and `scope` on `<td>` (#46).
  - `RL203` empty-table-header: `<th>` without text; the top-left corner cell
    of a table with row and column headers is allowed (#47).
  - `RL306` landmark-one-main: more than one `<main>` / `role="main"`, and
    full-page templates without one (#48).
- Document rules:
  - `RL603` document-title: full-page templates without a `<title>`, and empty
    titles (#49).
  - `RL604` valid-lang: `lang` / `xml:lang` values that are not BCP 47 language
    tags, with suggestions for country codes and language names (`ua` → `uk`,
    `english` → `en`), and `lang` / `xml:lang` with different languages (#50).
  - `RL605` meta-refresh: `<meta http-equiv="refresh">` with a delay (#51).
  - `RL606` obsolete-elements: `<marquee>` and `<blink>` (#52).
- Media rules:
  - `RL103` video-caption: `<video>` without a captions or subtitles track;
    muted videos are skipped (#53).
  - `RL104` svg-img-alt: `<svg role="img">` without a `<title>` or label (#54).
  - `RL105` object-alt: `<object>` without fallback text or a label, and
    `<embed>` without a `title` or label (#55).
  - `RL106` media-autoplay: `<video autoplay>` and `<audio autoplay>` without
    `muted` (#56).
- Form and keyboard rules:
  - `RL403` label-for-target: `<label for>` without a matching `id`, with hints
    when the `for` matches a field's `name` or a similar id (#57).
  - `RL506` duplicate-accesskey: the same `accesskey` used twice (#58).
- Demo templates for the new rules: `catalog/category.html`, a standalone
  `errors/500.html`, a landing page `promo/black_friday.html`,
  `pages/about.html` and `pages/contact.html`.

### Changed

- Variables that render HTML are treated as unknown markup instead of text:
  forms and form fields (`{{ form }}`, `{{ form.email }}`, `{{ field }}`,
  `{{ form.as_p }}`, `{{ field.errors }}`), `{{ block.super }}`, and the
  `|safe` and crispy-forms filters. Rules that look for ids, rows or other
  elements no longer guess about markup they cannot see.
- `{% block %}` in a child template (one with `{% extends %}`) is no longer
  treated as a slot for unknown markup by `RL403`: the block renders the
  content written in the template itself.

## [0.3.1] - 2026-10-21

### Added

- Python 3.14 is tested and supported.

### Changed

- Every pull request now builds the package, checks its PyPI metadata and
  contents, installs the wheel in a clean environment and runs the CLI from
  it, and tests the pre-commit hook.
- Releases are published only if the tag matches the package version and the
  tests, package checks and a smoke test of the wheel pass.
- Test coverage must stay at 95% or higher.

## [0.3.0] - 2026-10-21

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
- A documentation page for every rule in `docs/rules/`, with examples, WCAG
  references and suppression options; `ramplint --explain RL101` shows it in
  the terminal (#13).

### Changed

- Output formats live in a small registry, so a new format is a single
  decorated function (#8).

### Fixed

- `--list-rules` columns stay aligned for long rule names.

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

[Unreleased]: https://github.com/iLLcruS/ramplint/compare/0.5.0...HEAD
[0.5.0]: https://github.com/iLLcruS/ramplint/compare/0.4.1...0.5.0
[0.4.1]: https://github.com/iLLcruS/ramplint/compare/0.4.0...0.4.1
[0.4.0]: https://github.com/iLLcruS/ramplint/compare/0.3.1...0.4.0
[0.3.1]: https://github.com/iLLcruS/ramplint/compare/0.3.0...0.3.1
[0.3.0]: https://github.com/iLLcruS/ramplint/compare/0.2.1...0.3.0
[0.2.1]: https://github.com/iLLcruS/ramplint/compare/0.2.0...0.2.1
[0.2.0]: https://github.com/iLLcruS/ramplint/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/iLLcruS/ramplint/releases/tag/0.1.0
