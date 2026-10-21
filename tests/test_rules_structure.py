"""Structure rules: lists, landmarks, nested controls and table headers."""

from __future__ import annotations

import pytest

from ramplint import lint_source, select_rules


def messages(source: str, code: str) -> list[str]:
    return [v.message for v in lint_source(source, rules=select_rules([code]))]


# --------------------------------------------------------------------------
# RL304 list-structure
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "<ul><div>Item</div></ul>",
        "<ul><li>One</li><p>Two</p></ul>",
        '<ol><a href="/">Step</a></ol>',
        "<ul><div><li>Wrapped</li></div></ul>",
        "<div><li>Item</li></div>",
        '<html lang="en"><body><li>Item</li></body></html>',
        '<ul role="list"><span>Item</span></ul>',
    ],
)
def test_list_structure_violations(lint, source):
    assert lint(source, "RL304") == [("RL304", 1)]


@pytest.mark.parametrize(
    "source",
    [
        "<ul><li>One</li><li>Two</li></ul>",
        "<ol><li>One<ul><li>Nested</li></ul></li></ol>",
        "<menu><li><button>Copy</button></li></menu>",
        "<ul>{% for item in items %}<li>{{ item }}</li>{% empty %}<li>None</li>{% endfor %}</ul>",
        '<ul>{% include "menu/items.html" %}</ul>',
        "<ul>{% block items %}{% endblock %}</ul>",
        "<ul>{{ items_html }}</ul>",
        "<ul><script>init()</script><template><li>{{ x }}</li></template></ul>",
        '<ul role="tablist"><div role="tab">Tab</div></ul>',
        '<ul role="none"><div>Layout</div></ul>',
        '<ul role="{{ role }}"><div>Item</div></ul>',
        "<ul {{ attrs }}><div>Item</div></ul>",
        "<ul><div {{ attrs }}>Item</div></ul>",
        '<ul><div role="listitem">Item</div></ul>',
        '<div role="list"><li>Item</li></div>',
        "<div {{ attrs }}><li>Item</li></div>",
        # A partial included into a list elsewhere.
        "<li>{{ item }}</li>",
        '{% for link in links %}<li><a href="{{ link.url }}">{{ link }}</a></li>{% endfor %}',
        "<template><li>{{ item }}</li></template>",
    ],
)
def test_list_structure_ok(lint, source):
    assert lint(source, "RL304") == []


def test_list_structure_messages():
    assert messages("<ul><div>x</div></ul>", "RL304")[0].startswith(
        "<div> cannot be a direct child of <ul>"
    )
    assert "<li> is not inside <ul>, <ol> or <menu>" in messages("<p><li>x</li></p>", "RL304")[0]


def test_list_structure_reports_every_wrong_child(lint):
    source = "<ul>\n  <li>a</li>\n  <div>b</div>\n  <span>c</span>\n</ul>"
    assert lint(source, "RL304") == [("RL304", 3), ("RL304", 4)]


# --------------------------------------------------------------------------
# RL305 definition-list
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "<dl><p>Term</p></dl>",
        "<dl><dt>Term</dt><dd>Description</dd><span>Note</span></dl>",
        "<dl><div><p>Term</p></div></dl>",
        "<section><dt>Term</dt></section>",
        '<html lang="en"><body><dd>Description</dd></body></html>',
    ],
)
def test_definition_list_violations(lint, source):
    assert lint(source, "RL305") == [("RL305", 1)]


@pytest.mark.parametrize(
    "source",
    [
        "<dl><dt>Term</dt><dd>Description</dd></dl>",
        "<dl><div><dt>Term</dt><dd>Description</dd></div></dl>",
        "<dl>{% for k, v in specs %}<dt>{{ k }}</dt><dd>{{ v }}</dd>{% endfor %}</dl>",
        '<dl>{% include "specs.html" %}</dl>',
        "<dl><script></script><template><p>{{ x }}</p></template></dl>",
        '<dl role="presentation"><p>Layout</p></dl>',
        "<dl {{ attrs }}><p>Term</p></dl>",
        "<dl><div {{ attrs }}><p>Term</p></div></dl>",
        "<dl><div><dt>Term</dt><p {{ attrs }}>Description</p></div></dl>",
        "<div {{ attrs }}><dt>Term</dt></div>",
        # Partials included into a <dl> elsewhere.
        "<dt>{{ term }}</dt><dd>{{ description }}</dd>",
        '<div class="row"><dt>{{ term }}</dt><dd>{{ description }}</dd></div>',
    ],
)
def test_definition_list_ok(lint, source):
    assert lint(source, "RL305") == []


@pytest.mark.parametrize(
    "source",
    [
        "<dl><dd>Description without a term</dd></dl>",
        "<dl><dt>Term without a description</dt></dl>",
        "<dl><dt>A</dt><dd>a</dd><dt>B</dt></dl>",
        "<dl><div><dd>Orphaned</dd></div></dl>",
        "<dl><div><dt>Term</dt></div></dl>",
        "<dl><dt></dt><dd>Description</dd></dl>",
        "<dl><dt><i class='icon'></i></dt><dd>Description</dd></dl>",
        "<dt></dt>",
    ],
)
def test_definition_list_groups(lint, source):
    assert lint(source, "RL305") == [("RL305", 1)]


@pytest.mark.parametrize(
    "source",
    [
        "<dl><dt>A</dt><dt>B</dt><dd>Shared description</dd><dd>Another one</dd></dl>",
        "<dl><div><dt>A</dt><dd>a</dd></div><div><dt>B</dt><dd>b</dd></div></dl>",
        "<dl><script></script><dt>A</dt><template><dd>x</dd></template><dd>a</dd></dl>",
        "<dl><dt>{{ spec.name }}</dt><dd>{{ spec.value }}</dd></dl>",
        "<dl><dt>A</dt>{% if a %}<dd>a</dd>{% endif %}</dl>",
        # Terms or descriptions may be rendered at runtime.
        '<dl><dt>Price</dt>{% include "price_dd.html" %}</dl>',
        "<dl><dt>Price</dt>{{ price_html }}</dl>",
        "<dl><dd {{ attrs }}>a</dd></dl>",
        "<dl><div {{ attrs }}><dd>a</dd></div></dl>",
        '<dl><dt aria-hidden="true"></dt><dd>a</dd></dl>',
        "<dt>{% trans 'Weight' %}</dt>",
    ],
)
def test_definition_list_groups_ok(lint, source):
    assert lint(source, "RL305") == []


def test_definition_list_group_messages(lint):
    source = "<dl>\n<dt></dt>\n<div><dd>Orphaned</dd></div>\n</dl>"
    found = messages(source, "RL305")
    assert lint(source, "RL305") == [("RL305", 2), ("RL305", 2), ("RL305", 3)]
    assert any(m.startswith("<dt> is empty") for m in found)
    assert any(m.startswith("<dt> has no <dd> after it") for m in found)
    assert any(m.startswith("<dd> has no <dt> before it") for m in found)


def test_definition_list_messages():
    assert messages("<dl><p>x</p></dl>", "RL305")[0].startswith(
        "<p> cannot be a direct child of <dl>"
    )
    assert "<div> group" in messages("<dl><div><p>x</p></div></dl>", "RL305")[0]
    assert messages("<p><dd>x</dd></p>", "RL305")[0].startswith("<dd> is not inside a <dl>")


# --------------------------------------------------------------------------
# RL505 nested-interactive
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<a href="/cart"><button>Buy</button></a>',
        '<button><a href="/help">Help</a></button>',
        '<a href="/"><a href="/x">Inner</a></a>',
        '<button><input type="checkbox"></button>',
        "<button><select></select></button>",
        "<button><textarea></textarea></button>",
        '<a href="/"><details><summary>More</summary></details></a>',
        '<a href="/"><summary>More</summary></a>',
        '<a href="/"><span role="button">Like</span></a>',
        '<button><span role="checkbox" aria-checked="false">x</span></button>',
        '<a href="/"><div tabindex="0">Card</div></a>',
        '<a href="{{ product.url }}"><div class="card"><button>Add</button></div></a>',
    ],
)
def test_nested_interactive_violations(lint, source):
    assert lint(source, "RL505") == [("RL505", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<a href="/">Home</a><button>Menu</button>',
        "<a><button>Not a link</button></a>",
        "<button><span>Save</span><svg aria-hidden='true'></svg></button>",
        '<a href="/">{% include "icons/cart.html" %}</a>',
        '<button><input type="hidden" name="x"></button>',
        '<a href="/"><span tabindex="-1">x</span></a>',
        '<a href="/"><span tabindex="{{ ti }}">x</span></a>',
        '<a href="/"><span {{ attrs }}>x</span></a>',
        '<a href="/"><span role="img" aria-label="Star"></span></a>',
        '<button><label for="x">Label</label></button>',
        '<button><template><a href="/">x</a></template></button>',
        "<details><summary>More</summary><button>Inside details is fine</button></details>",
    ],
)
def test_nested_interactive_ok(lint, source):
    assert lint(source, "RL505") == []


def test_nested_interactive_message():
    msg = messages('<a href="/">\n<input type="checkbox"></a>', "RL505")[0]
    assert msg.startswith('<input type="checkbox"> is nested inside <a href> (line 1)')


def test_nested_interactive_reports_each_inner_control(lint):
    source = '<a href="/">\n<button>A</button>\n<button>B</button>\n</a>'
    assert lint(source, "RL505") == [("RL505", 2), ("RL505", 3)]


# --------------------------------------------------------------------------
# RL202 th-scope
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        '<th scope="column">Name</th>',
        '<th scope="rows">Name</th>',
        '<th scope="">Name</th>',
        '<th scope="header">Name</th>',
        '<td scope="row">Name</td>',
    ],
)
def test_th_scope_violations(lint, source):
    assert lint(f"<table><tr>{source}</tr></table>", "RL202") == [("RL202", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<th scope="col">Name</th>',
        '<th scope="row">Name</th>',
        '<th scope="rowgroup">Name</th>',
        '<th scope="colgroup">Name</th>',
        '<th scope="COL">Name</th>',
        '<th scope="{{ scope }}">Name</th>',
        "<th>Name</th>",
        "<td>Name</td>",
    ],
)
def test_th_scope_ok(lint, source):
    assert lint(f"<table><tr>{source}</tr></table>", "RL202") == []


@pytest.mark.parametrize(
    ("value", "suggestion"),
    [("column", "col"), ("columns", "col"), ("rows", "row"), ("colgrup", "colgroup")],
)
def test_th_scope_suggestion(value, suggestion):
    msg = messages(f'<th scope="{value}">x</th>', "RL202")[0]
    assert msg.endswith(f'did you mean scope="{suggestion}"?')


def test_th_scope_on_td_message():
    assert messages('<td scope="row">x</td>', "RL202")[0].startswith("scope only works on <th>")


# --------------------------------------------------------------------------
# RL203 empty-table-header
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "<table><tr><th></th><th>Price</th></tr><tr><td>1</td><td>2</td></tr></table>",
        "<table><tr><th>Name</th><th>&nbsp;</th></tr></table>",
        '<table><tr><th><i class="icon-sort"></i></th></tr></table>',
        '<table><tr><th><img src="sort.png" alt=""></th></tr></table>',
        "<table><tr><th>Q1</th><th></th></tr><tr><th>North</th><td>1</td></tr></table>",
        "<table><tr><th>Region</th></tr><tr><th></th><td>1</td></tr><tr><th>N</th></tr></table>",
        "<th></th>",
    ],
)
def test_empty_table_header_violations(lint, source):
    assert lint(source, "RL203") == [("RL203", 1)]


@pytest.mark.parametrize(
    "source",
    [
        '<table><tr><th scope="col">Name</th></tr></table>',
        "<th>{{ column.title }}</th>",
        '<th>{% trans "Price" %}</th>',
        '<th>{% include "headers/price.html" %}</th>',
        '<th><span class="visually-hidden">Actions</span></th>',
        '<th aria-label="Actions"></th>',
        '<th><img src="status.png" alt="Status"></th>',
        "<th {{ attrs }}></th>",
        '<th aria-hidden="true"></th>',
        '<table role="presentation"><tr><th></th></tr></table>',
        # Top-left corner of a table with column and row headers.
        "<table><tr><th></th><th>Q1</th></tr><tr><th>North</th><td>1</td></tr></table>",
        (
            "<table><thead><tr><th></th><th>Q1</th></tr></thead>"
            "<tbody>{% for r in rows %}<tr><th>{{ r.name }}</th><td>1</td></tr>{% endfor %}"
            "</tbody></table>"
        ),
    ],
)
def test_empty_table_header_ok(lint, source):
    assert lint(source, "RL203") == []


# --------------------------------------------------------------------------
# RL306 landmark-one-main
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "<main>One</main>\n<main>Two</main>",
        '<main>One</main>\n<div role="main">Two</div>',
        '<div role="main">One</div>\n<main role="main">Two</main>',
        "{% if a %}<main>a</main>{% endif %}\n<main>b</main>",
    ],
)
def test_landmark_one_main_duplicates(lint, source):
    assert lint(source, "RL306") == [("RL306", 2)]


def test_landmark_one_main_duplicate_message():
    msg = messages("<main>a</main>\n<main>b</main>", "RL306")[0]
    assert msg.startswith("Second main landmark (the first is on line 1)")


def test_landmark_one_main_missing_in_full_page(lint):
    source = '<!DOCTYPE html>\n<html lang="en">\n<head><title>Error</title></head>\n<body>\n'
    source += "<h1>Server error</h1>\n</body>\n</html>"
    assert lint(source, "RL306") == [("RL306", 4)]
    assert messages(source, "RL306")[0].startswith("Page has no main landmark")


def test_landmark_one_main_missing_without_body(lint):
    assert lint('<html lang="en"><p>Hi</p></html>', "RL306") == [("RL306", 1)]
    assert lint('<html lang="en"><body>Hi</body></html>', "RL306") == [("RL306", 1)]


@pytest.mark.parametrize(
    "source",
    [
        "<main>{% block content %}{% endblock %}</main>",
        '<html lang="en"><body><main>Content</main></body></html>',
        '<html lang="en"><body><div role="main">Content</div></body></html>',
        '<html lang="en"><body>{% block body %}{% endblock %}</body></html>',
        '<html lang="en"><body>{% include "layout.html" %}</body></html>',
        '<html lang="en"><body><div {{ attrs }}>Content</div></body></html>',
        '<html lang="en"><body><div role="{{ role }}">Content</div></body></html>',
        "{% if a %}<main>A</main>{% elif b %}<main>B</main>{% else %}<main>C</main>{% endif %}",
        "<main>Visible</main><main hidden>Inactive view</main>",
        "<template><main>Client-side view</main></template><main>Page</main>",
        '<main role="{{ role }}">One</main>',
        # Nothing to read: a page that runs a script and closes itself.
        '<html lang="en"><head><title>Bye</title></head><body><script>x()</script></body></html>',
        '<html lang="en"><head><title>Bye</title></head><script>close()</script></html>',
        # Partials and child templates: the main may be in the parent.
        "<div>Content</div>",
        '{% extends "base.html" %}{% block content %}<h1>Hi</h1>{% endblock %}',
    ],
)
def test_landmark_one_main_ok(lint, source):
    assert lint(source, "RL306") == []
