# Demo templates

A tiny, fictional Django shop ("Shoply") whose templates are **intentionally
inaccessible**. Use it to see ramplint in action:

```bash
ramplint examples/            # all 29 problems
ramplint examples/ --select RL4
ramplint examples/ --format json
```

| Template                                | Problems | What is wrong                                                                                     |
|-----------------------------------------|---------:|---------------------------------------------------------------------------------------------------|
| `templates/base.html`                   | 3        | `<html>` without `lang`, logo link whose only content is an image without `alt`                   |
| `templates/partials/navbar.html`        | 4        | Icon-only cart link, avatar link with an empty `alt`, search link with `tabindex="1"`, hamburger `<div role="button">` with no name |
| `templates/partials/footer.html`        | 4        | Social links that only contain an SVG, map `<iframe>` without a `title`, newsletter field labelled by a placeholder |
| `templates/accounts/login.html`         | 6        | Inputs and a `<select>` without labels, unnamed `<input type="button">`, icon-only submit button, the same `id` used twice |
| `templates/products/detail.html`        | 6        | Gallery images without `alt`, `<h1>` → `<h3>`, specs table without `<th>`, empty `<h2>`, unlabelled quantity, `<input type="image">` without `alt` |
| `templates/orders/list.html`            | 6        | One problem for each of six rules                                                                 |
| `templates/orders/list_fixed.html`      | 0        | The same page as `list.html`, fixed. Diff the two files to see the fixes                           |
| `templates/clean/tricky_but_valid.html` | 0        | Template patterns ramplint understands and does not report: `{{ form.as_table }}`, `{% include %}` inside tables, `id_for_label`, `{{ widget.attrs }}`, translated button labels, an `<iframe>` titled from a variable, the same `id` in `{% if %}` / `{% else %}` branches, `tabindex` 0 / -1 / from a variable and an inline `ramplint: ignore` |

Compare the broken and fixed order list side by side:

```bash
diff examples/templates/orders/list.html examples/templates/orders/list_fixed.html
```
