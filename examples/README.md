# Demo templates

A tiny, fictional Django shop ("Shoply") whose templates are **intentionally
inaccessible**. Use it to see ramplint in action:

```bash
ramplint examples/            # all 62 problems
ramplint examples/ --select RL4
ramplint examples/ --format json
```

| Template                                | Problems | What is wrong                                                                                     |
|-----------------------------------------|---------:|---------------------------------------------------------------------------------------------------|
| `templates/base.html`                   | 4        | `<html>` without `lang`, viewport that disables zoom, logo link whose only content is an image without `alt` |
| `templates/partials/navbar.html`        | 4        | Icon-only cart link, avatar link with an empty `alt`, search link with `tabindex="1"`, hamburger `<div role="button">` with no name |
| `templates/partials/footer.html`        | 5        | Social links that only contain an SVG, map `<iframe>` without a `title`, newsletter field labelled by a placeholder and with a typo in `autocomplete` |
| `templates/components/filters_dialog.html` | 6 | ARIA mistakes: misspelled role, misspelled `aria-labelledby`, `aria-hidden="yes"`, a switch without `aria-checked`, a checkbox role that cannot be focused, a focusable link inside `aria-hidden` |
| `templates/accounts/login.html`         | 7        | Inputs and a `<select>` without labels, unnamed `<input type="button">`, icon-only submit button, the same `id` used twice, a `javascript:` link used as a button |
| `templates/products/detail.html`        | 6        | Gallery images without `alt`, `<h1>` → `<h3>`, specs table without `<th>`, empty `<h2>`, unlabelled quantity, `<input type="image">` without `alt` |
| `templates/orders/list.html`            | 6        | One problem for each of six rules                                                                 |
| `templates/catalog/category.html`       | 5        | Category links placed straight in a `<ul>`, a product card link that wraps an "Add to cart" button, `scope="column"`, an empty `<th>` above the actions column, a `<dl>` row wrapped in a `<span>` |
| `templates/errors/500.html`             | 1        | A standalone error page (Django renders it without `base.html`) with no `<main>` landmark |
| `templates/promo/black_friday.html`     | 4        | A standalone landing page: `lang="english"`, no `<title>`, a redirect after 15 seconds and a `<marquee>` |
| `templates/pages/about.html`            | 4        | Media: a video without captions, an `<audio autoplay>` jingle, a chart `<svg role="img">` without a name and a PDF `<object>` without fallback text |
| `templates/pages/contact.html`          | 3        | `<label for="message">` pointing to `id="msg"` (also reported by RL401 for the `<textarea>`) and the same `accesskey` on a link and a button |
| `templates/orders/list_fixed.html`      | 0        | The same page as `list.html`, fixed. Diff the two files to see the fixes                           |
| `templates/clean/tricky_but_valid.html` | 0        | Template patterns ramplint understands and does not report: `{{ form.as_table }}`, `{% include %}` inside tables, `id_for_label`, `{{ widget.attrs }}`, valid `autocomplete` tokens, translated button labels, an `<iframe>` titled from a variable, the same `id` in `{% if %}` / `{% else %}` branches, real links (`#fragment`, named anchor, URL from a variable), `tabindex` 0 / -1 / from a variable, a zoomable viewport, valid ARIA (roles, states, references, hidden content with `tabindex="-1"`), lists filled by `{% for %}`, `{% include %}` and `{% block %}`, a tab list built on `<ul role="tablist">`, `<dl>` with `<div>` groups, valid `scope` values, a visually hidden header and an empty top-left corner cell, a card with a link and a separate button, an immediate `meta refresh` redirect, valid and dynamic `lang` values on parts of the page, captioned and muted background videos, a named `<svg role="img">`, a PDF `<object>` with a download link, fields rendered one by one with their labels, unique access keys, focusable custom controls (tabindex, roving tabindex, a listbox with `aria-activedescendant`), and an inline `ramplint: ignore` |

Compare the broken and fixed order list side by side:

```bash
diff examples/templates/orders/list.html examples/templates/orders/list_fixed.html
```

## Django project

`django_project/` is a small Django project (it does not need Django installed)
that shows how ramplint finds templates and follows `{% extends %}` and
`{% include %}`:

```bash
cd examples/django_project
ramplint --list-templates     # settings package, two apps, a Jinja2 folder
ramplint                      # 7 problems; static/vendor/docs.html is skipped
```

| Template                                          | Problems | What is wrong                                                                 |
|---------------------------------------------------|---------:|-------------------------------------------------------------------------------|
| `catalog/templates/catalog/product_list.html`     | 3        | No `{% block title %}` (the page title stays empty), `<h3>` right after the `<h1>` of `base.html`, a second `<main>` inside the block `base.html` wraps in `<main>` |
| `catalog/jinja2/catalog/badge.jinja`              | 1        | Image without `alt` in a Jinja2 template from the app's `jinja2/` folder       |
| `accounts/templates/accounts/profile.html`        | 1        | `{% for field in form %}{{ field }}` without `{{ field.label_tag }}`: inputs without labels |
| `accounts/forms.py`                               | 2        | `label=""` with a placeholder, and a custom widget whose template drops `widget.attrs` (so the input has no id) |
| `accounts/templates/accounts/login.html`          | 0        | Fields rendered by Django (`{{ form.username }}`): their ids are unknown, so labels are not checked |
| `templates/base.html`, `templates/partials/*.html`| 0        | The base template; the label in `product_list.html` points to an id in the included `search.html` |
