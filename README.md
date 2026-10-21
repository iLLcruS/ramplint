<h1 align="center">ramplint</h1>

<p align="center">
  <strong>Accessibility linter for Django and Jinja2 templates.</strong><br>
  Catch WCAG problems in your <code>.html</code> templates before they reach production.
</p>

<p align="center">
  <a href="https://github.com/iLLcruS/ramplint/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/iLLcruS/ramplint/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/ramplint/"><img alt="PyPI" src="https://img.shields.io/pypi/v/ramplint.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue.svg">
  <a href="https://github.com/iLLcruS/ramplint/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green.svg"></a>
  <a href="https://ko-fi.com/innerexcept"><img alt="Support on Ko-fi" src="https://img.shields.io/badge/Ko--fi-support-72a4f2?logo=ko-fi&logoColor=white"></a>
</p>

---

Generic HTML linters choke on `{% if %}`, `{{ variables }}` and `{% include %}`,
and browser-based checkers only see the pages you remember to open.
**ramplint** reads your templates directly, understands the template syntax,
and reports problems with the exact line and column in the template source:

<p align="center">
  <img src="https://raw.githubusercontent.com/iLLcruS/ramplint/main/docs/demo.svg" alt="Terminal output of ramplint reporting six accessibility problems in a Django product page template">
</p>

## Try it in 30 seconds

The repository ships with a small demo shop in [`examples/`](https://github.com/iLLcruS/ramplint/tree/main/examples): a
deliberately inaccessible set of Django templates that triggers every rule,
plus a file full of tricky-but-valid template patterns that must stay silent.

```bash
git clone https://github.com/iLLcruS/ramplint.git
cd ramplint
pip install .
ramplint examples/
```

```console
examples/templates/base.html:3:1: RL601 <html> is missing a lang attribute; add e.g. lang="en" or lang="{{ LANGUAGE_CODE }}" [html-lang]
examples/templates/base.html:6:3: RL602 Viewport meta tag: user-scalable=no disables zooming; maximum-scale=1 limits zoom below 200%. Users must be able to zoom; remove these settings [viewport-zoom]
examples/templates/base.html:13:5: RL502 <a> link has no accessible name; add text, an aria-label, or alt text on the image inside it [link-name]
examples/templates/base.html:13:45: RL101 <img> is missing an alt attribute (use alt="" for decorative images) [img-alt]
examples/templates/accounts/login.html:10:3: RL401 <input type="text"> has no associated label; add an id and a matching <label for>, or wrap it in a <label> (a placeholder is not a label) [form-label]
...
examples/templates/products/detail.html:28:3: RL101 <input type="image"> needs a non-empty alt attribute describing the action [img-alt]

Found 37 problems in 7 of 9 files.
```

See [`examples/README.md`](https://github.com/iLLcruS/ramplint/blob/main/examples/README.md) for what each demo template contains.

## Highlights

- **Template-aware.** Django and Jinja2 tags, variables and comments are understood, not stripped blindly.
- **Low noise.** If something is only known at render time (`{% include %}`, `{{ widget.attrs }}`, `{% block %}`), ramplint assumes the best and stays quiet.
- **Zero dependencies.** Pure Python standard library (plus `tomli` on Python < 3.11).
- **Made for CI.** Exit codes, JSON output, GitHub Actions annotations and a pre-commit hook.
- **Fast.** No browser and no rendering. A whole project is checked in well under a second.

## Installation

```bash
pip install ramplint
```

## Usage

```bash
ramplint                        # lint every template under the current directory
ramplint templates/ shop/templates/base.html
ramplint --select RL1,RL5       # only image and control rules
ramplint --ignore heading-order # rules can be referenced by code or name
ramplint --format json          # machine-readable output
ramplint --statistics          # problems per rule, most frequent first
ramplint -o report.json --format json  # save the report to a file
ramplint -o a11y-report.html --format html  # shareable HTML report
ramplint --list-rules
ramplint --explain RL303        # what a rule checks and how to fix it
```

By default ramplint looks at `.html`, `.htm`, `.jinja`, `.jinja2`, `.j2` and
`.djhtml` files and skips folders such as `node_modules`, `.venv`, `build` and `dist`.
Files passed explicitly are always checked, whatever their extension.

### Output formats

| Format   | Use it for                                                       |
|----------|------------------------------------------------------------------|
| `text`   | Reading in the terminal (default; colored when it is a terminal) |
| `json`   | Scripts, dashboards and other tools                              |
| `github` | Annotations in GitHub pull requests (default inside Actions)     |
| `html`   | A single self-contained page to share with your team or a client |
| `sarif`  | GitHub Code Scanning and other security dashboards               |

`--output FILE` writes the report to a file and prints a one-line summary
instead. Missing folders are created, and colors are never written to files.

The HTML report needs no internet connection, so it can be attached to an email
or stored as a CI artifact. Every problem comes with the surrounding template
lines, rule names link to their documentation, and you can filter by rule or
template. It follows the light or dark theme of the viewer's system, and it
passes ramplint itself.

<p align="center">
  <img src="https://raw.githubusercontent.com/iLLcruS/ramplint/main/docs/html-report.png" alt="HTML report: a blue header with 32 problems in 6 templates, a table of problems by rule and a list of templates with problems" width="800">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/iLLcruS/ramplint/main/docs/html-report-details.png" alt="HTML report details: filters by rule and template, and each problem with the highlighted line of template source" width="800">
</p>

`--statistics` replaces the list of problems with a count per rule, which helps
decide what to fix first:

```console
$ ramplint examples/ --statistics
6  RL401  form-label
6  RL502  link-name
4  RL101  img-alt
4  RL501  button-name
2  RL201  table-header
2  RL301  heading-order
1  RL102  iframe-title
1  RL302  empty-heading
1  RL303  duplicate-id
1  RL402  autocomplete-valid
1  RL503  no-positive-tabindex
1  RL504  anchor-is-valid
1  RL601  html-lang
1  RL602  viewport-zoom
1  RL701  aria-role
1  RL702  aria-valid-attr
1  RL703  aria-valid-attr-value
1  RL704  aria-required-attr
1  RL705  aria-hidden-focus

Found 37 problems in 7 of 9 files.
```

It works with `--format text` (default) and `--format json`.

| Exit code | Meaning                      |
|-----------|------------------------------|
| `0`       | No problems found            |
| `1`       | Problems found               |
| `2`       | Usage or configuration error |

## Rules

| Code    | Name            | What it checks                                                                           | WCAG             |
|---------|-----------------|------------------------------------------------------------------------------------------|------------------|
| [`RL101`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL101.md) | `img-alt`       | `<img>` has an `alt` attribute; `<input type="image">` and `<area>` have non-empty `alt` | 1.1.1 (A)        |
| [`RL102`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL102.md) | `iframe-title`  | `<iframe>` has a `title` describing its content                                          | 4.1.2 (A)        |
| [`RL201`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL201.md) | `table-header`  | Data tables use real `<th>` header cells                                                 | 1.3.1 (A)        |
| [`RL301`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL301.md) | `heading-order` | Heading levels do not skip (`<h2>` → `<h4>`)                                             | 1.3.1 (A)        |
| [`RL302`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL302.md) | `empty-heading` | Headings are not empty                                                                   | 2.4.6 (AA)       |
| [`RL303`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL303.md) | `duplicate-id`  | `id` values are unique (same id in `{% if %}` / `{% else %}` branches is allowed)        | 1.3.1 (A)        |
| [`RL401`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL401.md) | `form-label`    | `<input>`, `<select>` and `<textarea>` have an associated `<label>`                      | 1.3.1, 4.1.2 (A) |
| [`RL402`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL402.md) | `autocomplete-valid` | `autocomplete` uses valid autofill tokens (catches typos like `emial`)              | 1.3.5 (AA)       |
| [`RL501`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL501.md) | `button-name`   | Buttons (including icon-only buttons) have an accessible name                            | 4.1.2 (A)        |
| [`RL502`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL502.md) | `link-name`     | Links have an accessible name                                                            | 2.4.4, 4.1.2 (A) |
| [`RL503`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL503.md) | `no-positive-tabindex` | `tabindex` is not greater than `0`                                                | 2.4.3 (A)        |
| [`RL504`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL504.md) | `anchor-is-valid` | Links have a real target (no `href="#"`, `javascript:` or click-only `<a>`)        | 2.1.1 (A)        |
| [`RL601`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL601.md) | `html-lang`     | `<html>` declares the page language                                                      | 3.1.1 (A)        |
| [`RL602`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL602.md) | `viewport-zoom` | `<meta name="viewport">` does not disable zoom (`user-scalable=no`, `maximum-scale` < 2) | 1.4.4 (AA)       |
| [`RL701`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL701.md) | `aria-role` | `role` is a real, non-abstract WAI-ARIA role (catches typos like `dailog`) | 4.1.2 (A) |
| [`RL702`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL702.md) | `aria-valid-attr` | `aria-*` attributes exist (catches `aria-lable`, `aria-labeledby`) | 4.1.2 (A) |
| [`RL703`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL703.md) | `aria-valid-attr-value` | ARIA values match their type (`aria-hidden="yes"`, missing `aria-labelledby` ids) | 4.1.2 (A) |
| [`RL704`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL704.md) | `aria-required-attr` | Roles have their required states (`role="switch"` needs `aria-checked`) | 4.1.2 (A) |
| [`RL705`](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/RL705.md) | `aria-hidden-focus` | Nothing focusable inside `aria-hidden="true"` | 4.1.2 (A) |

Every rule has its own page with examples and the reasoning behind it: see
[docs/rules](https://github.com/iLLcruS/ramplint/blob/main/docs/rules/README.md),
or run `ramplint --explain RL101` in the terminal.

<details>
<summary><strong>Examples for every rule</strong></summary>

#### RL101 `img-alt`

```django
{# ✗ #} <img src="{% static 'logo.png' %}">
{# ✓ #} <img src="{% static 'logo.png' %}" alt="ACME">
{# ✓ #} <img src="{% static 'divider.png' %}" alt="">   {# decorative #}
{# ✓ #} <img src="{{ product.image.url }}" alt="{{ product.name }}">
```

#### RL102 `iframe-title`

```django
{# ✗ #} <iframe src="https://www.youtube.com/embed/{{ video.id }}"></iframe>
{# ✓ #} <iframe src="https://www.youtube.com/embed/{{ video.id }}" title="{{ video.title }}"></iframe>
```

Frames hidden with `aria-hidden="true"` are skipped.

#### RL201 `table-header`

```django
{# ✗ #} <table><tr><td>Name</td><td>Price</td></tr>…</table>
{# ✓ #} <table><tr><th scope="col">Name</th><th scope="col">Price</th></tr>…</table>
{# ✓ #} <table role="presentation">…</table>              {# layout table #}
```

`role="columnheader"` on a `<td>` is not accepted. Use a real `<th>`.
Tables whose rows come from `{% include %}`, `{% block %}` or `{{ form.as_table }}`
are skipped because their content is not visible in the template.

#### RL301 `heading-order`

```django
{# ✗ #} <h2>Orders</h2> <h4>Recent</h4>
{# ✓ #} <h2>Orders</h2> <h3>Recent</h3>
```

The first heading in a file sets the baseline. A child template that starts at
`<h2>` (because `base.html` owns the `<h1>`) is fine.

#### RL302 `empty-heading`

```django
{# ✗ #} <h2><i class="icon-star"></i></h2>
{# ✓ #} <h2>{% trans "Favourites" %}</h2>
```

#### RL303 `duplicate-id`

```django
{# ✗ #} <p id="help">…</p> … <p id="help">…</p>
{# ✓ #} {% if user.is_authenticated %}<p id="greeting">…</p>{% else %}<p id="greeting">…</p>{% endif %}
```

ramplint knows which `{% if %}` / `{% elif %}` / `{% else %}` (and `{% for %}` /
`{% empty %}`) branch an element is in, so the same id in mutually exclusive
branches is not reported. Ids built from variables are skipped.

#### RL401 `form-label`

```django
{# ✗ #} <input type="email" name="email" placeholder="Email">
{# ✓ #} <label for="email">Email</label> <input type="email" id="email" name="email">
{# ✓ #} <label>Email <input type="email" name="email"></label>
{# ✓ #} <input type="search" name="q" aria-label="Search">
```

Hidden, submit, reset, button and image inputs are not checked. Neither are
widgets whose attributes are rendered dynamically (`<input {{ widget.attrs }}>`).

#### RL402 `autocomplete-valid`

```django
{# ✗ #} <input type="email" name="email" autocomplete="emial" aria-label="Email">
{# ✗ #} <input name="phone" autocomplete="mobile street-address" aria-label="Phone">
{# ✓ #} <input name="email" autocomplete="email" aria-label="Email">
{# ✓ #} <input name="ship" autocomplete="section-gift shipping street-address" aria-label="Address">
```

A typo in `autocomplete` silently breaks autofill and password managers.
ramplint validates the full token grammar from the HTML spec and suggests the
closest valid token.

#### RL501 `button-name`

```django
{# ✗ #} <button><i class="fa fa-trash"></i></button>
{# ✓ #} <button aria-label="{% trans 'Delete' %}"><i class="fa fa-trash" aria-hidden="true"></i></button>
{# ✓ #} <button><span class="visually-hidden">Delete</span><i class="fa fa-trash"></i></button>
```

#### RL502 `link-name`

```django
{# ✗ #} <a href="{% url 'cart' %}"><svg>…</svg></a>
{# ✓ #} <a href="{% url 'cart' %}"><svg><title>Cart</title>…</svg></a>
{# ✓ #} <a href="/"><img src="logo.png" alt="ACME home"></a>
```

#### RL503 `no-positive-tabindex`

```django
{# ✗ #} <a href="{% url 'search' %}" tabindex="1">Search</a>
{# ✓ #} <div role="button" tabindex="0">Menu</div>
{# ✓ #} <div id="dialog" tabindex="-1">…</div>
```

A positive `tabindex` moves the element to the front of the keyboard focus
order, ahead of everything else on the page. Reorder the markup instead.

#### RL504 `anchor-is-valid`

```django
{# ✗ #} <a href="#" onclick="addToWishlist()">Add to wishlist</a>
{# ✗ #} <a href="javascript:void(0)">Open chat</a>
{# ✗ #} <a onclick="openMenu()">Menu</a>
{# ✓ #} <button type="button" onclick="addToWishlist()">Add to wishlist</button>
{# ✓ #} <a href="#reviews">Jump to reviews</a>
```

Links navigate, buttons act. A fake link is missing from the keyboard focus
order (no `href`) or does not react to the Space key like a button would.

#### RL601 `html-lang`

```django
{# ✗ #} <html>
{# ✓ #} <html lang="{{ LANGUAGE_CODE }}">
```

#### RL602 `viewport-zoom`

```django
{# ✗ #} <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
{# ✗ #} <meta name="viewport" content="width=device-width, maximum-scale=1">
{# ✓ #} <meta name="viewport" content="width=device-width, initial-scale=1">
```

Low-vision users rely on pinch-to-zoom; WCAG requires text to be resizable up to 200%.

#### RL701–RL705: ARIA

```django
{# ✗ #} <div role="dailog" aria-modal="true">…</div>
{# ✗ #} <button aria-lable="Close">×</button>
{# ✗ #} <div class="backdrop" aria-hidden="yes"></div>
{# ✗ #} <div role="switch" tabindex="0">Dark mode</div>
{# ✗ #} <div aria-hidden="true"><a href="/">Home</a></div>
{# ✓ #} <div role="switch" tabindex="0" aria-checked="false">Dark mode</div>
{# ✓ #} <div aria-hidden="true"><a href="/" tabindex="-1">Home</a></div>
```

</details>

## How templates are handled

Before parsing, every template token is replaced by a placeholder of the same
length, so positions in the report always match your source:

| Template code                                                | Treated as                      |
|--------------------------------------------------------------|---------------------------------|
| `{{ variable }}`, `{% trans %}`, `{% url %}`, `{% static %}` | Text that exists at runtime     |
| `{% include %}`, `{% block %}`, custom tags                  | Unknown markup (rules back off) |
| `{% if %}`, `{% for %}`, `{% with %}`, ...                   | Nothing (control flow)          |
| `{# ... #}`, `{% comment %}...{% endcomment %}`              | Nothing                         |

Both branches of an `{% if %}` are checked, so a problem in either one is reported.

## Suppressing problems

```django
<img src="spacer.gif"> {# ramplint: ignore RL101 #}

{# ramplint: ignore img-alt, link-name #}
<a href="/"><img src="logo.png"></a>

{# ramplint: ignore-file #}
```

`ignore` applies to its own line and the next one. With no codes it silences
every rule. HTML comments work too: `<!-- ramplint: ignore RL201 -->`.

## Configuration

Add a `[tool.ramplint]` section to `pyproject.toml`. Command-line options take
precedence over it.

```toml
[tool.ramplint]
select = ["RL"]                          # default: all rules
ignore = ["RL301"]
exclude = ["*/admin/*", "templates/vendor/*"]
extensions = [".html", ".txt"]
```

## pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/iLLcruS/ramplint
    rev: 0.3.1
    hooks:
      - id: ramplint
```

## GitHub Actions

When `GITHUB_ACTIONS=true`, ramplint switches to the `github` format and
problems appear as annotations right in the pull request diff.

```yaml
- run: pip install ramplint
- run: ramplint templates/
```

### GitHub Code Scanning

With `--format sarif`, problems also show up in the repository's
**Security → Code scanning** tab, where they are tracked over time and can be
dismissed with a reason. Code scanning is free for public repositories; private
repositories need GitHub Advanced Security.

```yaml
name: Accessibility

on: [push, pull_request]

jobs:
  ramplint:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ramplint
      # --exit-zero: let Code Scanning decide whether the check fails
      - run: ramplint templates/ --format sarif -o ramplint.sarif --exit-zero
      - uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: ramplint.sarif
          category: ramplint
```

## Python API

```python
from ramplint import lint_source, select_rules

for problem in lint_source('<img src="a.png">', rules=select_rules(["RL1"])):
    print(problem.line, problem.col, problem.code, problem.message)
```

## Limitations

ramplint is a static checker. It catches structural problems early and cheaply,
but it cannot judge colour contrast or focus order, or tell whether an `alt`
text is actually meaningful. Use it together with manual testing and a runtime
tool such as axe.

## Roadmap

- [ ] More rules: `<iframe title>`, duplicate `id`s, `autocomplete` on personal-data inputs
- [ ] `aria-*` attribute and role validation
- [ ] `--fix` for safe autofixes (e.g. `scope="col"` on header rows)
- [ ] SARIF output for GitHub code scanning
- [ ] Follow `{% extends %}` / `{% include %}` to check heading order across templates

## Contributing

Bug reports, especially about false positives, are very welcome.
See [CONTRIBUTING.md](https://github.com/iLLcruS/ramplint/blob/main/CONTRIBUTING.md).

## Feedback and support

Questions, ideas, or using ramplint in your project? Open an
[issue](https://github.com/iLLcruS/ramplint/issues) or email me at
[rostovskii.1020@gmail.com](mailto:rostovskii.1020@gmail.com).

ramplint is free and built in my spare time. If it saved you time, you can
buy me a coffee:

<a href="https://ko-fi.com/innerexcept"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support me on Ko-fi" height="36"></a>

## License

[MIT](https://github.com/iLLcruS/ramplint/blob/main/LICENSE) © Vladyslav Rostovskyi
