# Demo templates

A tiny, fictional Django shop ("Shoply") whose templates are **intentionally
inaccessible**. Use it to see ramplint in action:

```bash
ramplint examples/            # all 47 problems
ramplint examples/ --select RL4
ramplint examples/ --format json
```

| Template                                | Problems | What is wrong                                                                                     |
|-----------------------------------------|---------:|---------------------------------------------------------------------------------------------------|
| `templates/base.html`                   | 4        | `<html>` without `lang`, viewport that disables zoom, logo link whose only content is an image without `alt` |
| `templates/partials/navbar.html`        | 4        | Icon-only cart link, avatar link with an empty `alt`, search link with `tabindex="1"`, hamburger `<div role="button">` with no name |
| `templates/partials/footer.html`        | 5        | Social links that only contain an SVG, map `<iframe>` without a `title`, newsletter field labelled by a placeholder and with a typo in `autocomplete` |
| `templates/components/filters_dialog.html` | 5 | ARIA mistakes: misspelled role, misspelled `aria-labelledby`, `aria-hidden="yes"`, a switch without `aria-checked`, a focusable link inside `aria-hidden` |
| `templates/accounts/login.html`         | 7        | Inputs and a `<select>` without labels, unnamed `<input type="button">`, icon-only submit button, the same `id` used twice, a `javascript:` link used as a button |
| `templates/products/detail.html`        | 6        | Gallery images without `alt`, `<h1>` → `<h3>`, specs table without `<th>`, empty `<h2>`, unlabelled quantity, `<input type="image">` without `alt` |
| `templates/orders/list.html`            | 6        | One problem for each of six rules                                                                 |
| `templates/catalog/category.html`       | 5        | Category links placed straight in a `<ul>`, a product card link that wraps an "Add to cart" button, `scope="column"`, an empty `<th>` above the actions column, a `<dl>` row wrapped in a `<span>` |
| `templates/errors/500.html`             | 1        | A standalone error page (Django renders it without `base.html`) with no `<main>` landmark |
| `templates/promo/black_friday.html`     | 4        | A standalone landing page: `lang="english"`, no `<title>`, a redirect after 15 seconds and a `<marquee>` |
| `templates/orders/list_fixed.html`      | 0        | The same page as `list.html`, fixed. Diff the two files to see the fixes                           |
| `templates/clean/tricky_but_valid.html` | 0        | Template patterns ramplint understands and does not report: `{{ form.as_table }}`, `{% include %}` inside tables, `id_for_label`, `{{ widget.attrs }}`, valid `autocomplete` tokens, translated button labels, an `<iframe>` titled from a variable, the same `id` in `{% if %}` / `{% else %}` branches, real links (`#fragment`, named anchor, URL from a variable), `tabindex` 0 / -1 / from a variable, a zoomable viewport, valid ARIA (roles, states, references, hidden content with `tabindex="-1"`), lists filled by `{% for %}`, `{% include %}` and `{% block %}`, a tab list built on `<ul role="tablist">`, `<dl>` with `<div>` groups, valid `scope` values, a visually hidden header and an empty top-left corner cell, a card with a link and a separate button, an immediate `meta refresh` redirect, valid and dynamic `lang` values on parts of the page, and an inline `ramplint: ignore` |

Compare the broken and fixed order list side by side:

```bash
diff examples/templates/orders/list.html examples/templates/orders/list_fixed.html
```
