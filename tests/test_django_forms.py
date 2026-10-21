"""Django forms: fields rendered without labels (RL404), forms.py (RL405, RL406)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ramplint import lint_source, select_rules
from ramplint.linter import lint_file, lint_python_source
from ramplint.project.templates import TemplateIndex
from ramplint.project.workspace import Workspace
from ramplint.pyforms import is_forms_module


def messages(source: str, code: str) -> list[str]:
    return [v.message for v in lint_source(source, rules=select_rules([code]))]


def python(source: str, *codes: str, index=None) -> list[tuple[str, int]]:
    rules = select_rules(list(codes)) if codes else None
    found = lint_python_source(textwrap.dedent(source), "forms.py", rules=rules, index=index)
    return [(v.code, v.line) for v in found]


# --------------------------------------------------------------------------
# RL404 field-label
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "{% for field in form %}{{ field }}{% endfor %}",
        "{% for field in form.visible_fields %}<div>{{ field }}</div>{% endfor %}",
        "{% for field in contact_form %}{{ field }}{% endfor %}",
        "<p>Email</p> {{ form.email }}",
        "{{ user_form.email }}",
        '{{ form.email|add_class:"input" }}',
        '{{ form.email|attr:"placeholder:Email" }}',
        '{% render_field form.email class="input" %}',
        "{% for field in form %}{% render_field field %}{% endfor %}",
        "{% for field in form %}<label>{{ field.label }}</label>{{ field }}{% endfor %}",
    ],
)
def test_field_label_violations(lint, source):
    assert lint(source, "RL404") == [("RL404", 1)]


@pytest.mark.parametrize(
    "source",
    [
        "{% for field in form %}{{ field.label_tag }}{{ field }}{% endfor %}",
        '{% for f in form %}<label for="{{ f.id_for_label }}">{{ f.label }}</label>{{ f }}'
        "{% endfor %}",
        "{% for field in form %}{{ field.as_field_group }}{% endfor %}",
        '<label for="{{ form.email.auto_id }}">Email</label>{{ form.email }}',
        '<label for="id_email">Email</label>{{ form.email }}',
        "<label>{{ form.email.label }} {{ form.email }}</label>",
        "{{ form }}{{ form.as_p }}{{ form.as_div }}{{ form.errors }}{{ form.non_field_errors }}",
        "{{ form.email|as_crispy_field }}",
        '{% render_field form.q aria-label="Search" %}',
        "{% for field in form.hidden_fields %}{{ field }}{% endfor %}",
        "{% for field in form %}{% if field.is_hidden %}{{ field }}{% else %}"
        "{{ field.label_tag }}{{ field }}{% endif %}{% endfor %}",
        "{{ form.next }}{{ form.user_id }}{{ form.csrf_token }}",
        '<div style="display: none">{{ form.save_for_later }}</div>',
        "<div hidden>{{ form.DELETE }}</div>",
        "<h2>{{ form.title }}</h2>",
        '<input value="{{ form.email }}">',
        "{% for field in address.fields %}{{ field }}{% endfor %}",
        "{{ field }}",  # e.g. a partial: what `field` is depends on the include
        "{{ product.name }}",
        "{{ inline_admin_form.original }}",
    ],
)
def test_field_label_ok(lint, source):
    assert lint(source, "RL404") == []


def test_field_label_message_and_position(lint):
    source = "<form>\n  {% for field in form %}\n    {{ field }}\n  {% endfor %}\n</form>"
    assert lint(source, "RL404") == [("RL404", 3)]
    assert messages(source, "RL404") == [
        "{{ field }} renders only the input, without its <label>; add {{ field.label_tag }} "
        '(or <label for="{{ field.id_for_label }}">), or render {{ field.as_field_group }}'
    ]
    render = messages('{% render_field form.email class="x" %}', "RL404")[0]
    assert render.startswith("{% render_field form.email %} renders only the input")


def test_field_label_without_source():
    from ramplint import dom
    from ramplint.rules.forms import field_label

    assert list(field_label(dom.parse("<p></p>"))) == []


# --------------------------------------------------------------------------
# RL405 form-label-empty
# --------------------------------------------------------------------------


def test_empty_labels_in_form_classes():
    source = """
        from django import forms
        from django.utils.translation import gettext_lazy as _

        class ContactForm(forms.Form):
            email = forms.EmailField(label="", widget=forms.EmailInput(attrs={"placeholder": "x"}))
            name = forms.CharField(label=_(""))
            title = forms.CharField(label=" ")
            ok = forms.CharField(label=_("Name"))
            default = forms.CharField()
            search = forms.CharField(label="", widget=forms.TextInput(attrs={"aria-label": "S"}))
            hidden = forms.CharField(label="", widget=forms.HiddenInput)
            hidden2 = forms.CharField(label="", widget=forms.HiddenInput())
            dynamic = forms.CharField(label=make_label())

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.fields["ok"].label = ""
                self.fields["ok"].label = "Fine"
                self.other.label = ""

        class ProfileForm(BaseProfileForm):
            class Meta:
                labels = {"bio": "", "phone": "Phone", "q": "", "h": "", 1: ""}
                widgets = {"q": forms.TextInput(attrs={"title": "Q"}), "h": forms.HiddenInput()}

        class NotAForm:
            email = forms.EmailField(label="")

        class PriceForm(forms.Form):
            def __init__(self, *args, **kwargs):
                for pk in ids:
                    self.fields[f"price_{pk}"] = forms.DecimalField(label="")
                    self.fields["named"] = forms.DecimalField(label="", required=False)
                    self.fields["ok"] = forms.DecimalField(label="Price")
                    self.fields["h"] = forms.DecimalField(label="", widget=forms.HiddenInput)
                    self.fields["a"] = forms.DecimalField(
                        label="", widget=forms.NumberInput(attrs={"aria-label": "Price"})
                    )
                    other["x"] = forms.DecimalField(label="")
    """
    assert python(source, "RL405") == [
        ("RL405", 6),
        ("RL405", 7),
        ("RL405", 8),
        ("RL405", 18),
        ("RL405", 24),
        ("RL405", 33),
        ("RL405", 34),
    ]


def test_empty_label_messages():
    source = (
        "class F(forms.Form):\n"
        '    email = forms.EmailField(label="", widget=forms.EmailInput('
        'attrs={"placeholder": "Email"}))\n'
        '    name = forms.CharField(label="")\n'
    )
    found = lint_python_source(source, "forms.py", rules=select_rules(["RL405"]))
    assert found[0].message.startswith('Field "email" has an empty label')
    assert "(a placeholder is not a label)" in found[0].message
    assert "placeholder" not in found[1].message
    assert (found[0].line, found[0].col) == (2, 36)


def test_meta_without_dicts():
    source = """
        class F(forms.ModelForm):
            class Meta:
                labels = make_labels()
                model = Thing
    """
    assert python(source, "RL405") == []


# --------------------------------------------------------------------------
# RL406 widget-id
# --------------------------------------------------------------------------


def test_id_for_label_returning_nothing():
    source = '''
        class A(forms.Widget):
            def id_for_label(self, id_, index=None):
                """No id."""
                return None

        class B(forms.TextInput):
            def id_for_label(self, id_):
                return ""

        class C(forms.Select):
            def id_for_label(self, id_):
                return

        class D(forms.RadioSelect):
            def id_for_label(self, id_, index=None):
                if index is None:
                    return ""
                return super().id_for_label(id_, index)

        class E(forms.TextInput):
            def id_for_label(self, id_):
                return id_

        class NotAWidget:
            def id_for_label(self, id_):
                return None
    '''
    assert python(source, "RL406") == [("RL406", 3), ("RL406", 8), ("RL406", 12)]


@pytest.fixture
def widgets(tmp_path) -> TemplateIndex:
    folder = tmp_path / "templates" / "widgets"
    folder.mkdir(parents=True)
    (folder / "drops.html").write_text('<input type="text" name="{{ widget.name }}">')
    (folder / "keeps.html").write_text(
        '<input name="{{ widget.name }}"{% include "django/forms/widgets/attrs.html" %}>'
    )
    (folder / "extends.html").write_text('{% extends "django/forms/widgets/input.html" %}')
    (folder / "text.html").write_text("<span>{{ widget.value }}</span>")
    return TemplateIndex([tmp_path / "templates"], (".html",))


def test_widget_templates(widgets):
    source = """
        class Drops(forms.Widget):
            template_name = "widgets/drops.html"

        class Keeps(forms.Widget):
            template_name = "widgets/keeps.html"

        class Extends(forms.TextInput):
            template_name = "widgets/extends.html"

        class TextOnly(forms.Widget):
            template_name = "widgets/text.html"

        class Missing(forms.Widget):
            template_name = "widgets/missing.html"

        class Dynamic(forms.Widget):
            template_name = TEMPLATE
    """
    assert python(source, "RL406", index=widgets) == [("RL406", 3)]
    assert python(source, "RL406") == []  # no project: templates are unknown


# --------------------------------------------------------------------------
# Python modules: suppressions, discovery, CLI
# --------------------------------------------------------------------------


def test_python_suppressions():
    source = """
        class F(forms.Form):
            a = forms.CharField(label="")  # ramplint: ignore RL405
            # ramplint: ignore form-label-empty
            b = forms.CharField(label="")
            c = forms.CharField(label="")  # ramplint: ignore

            d = forms.CharField(label="")  # ramplint: ignore RL101
    """
    assert python(source, "RL405") == [("RL405", 8)]
    assert python("# ramplint: ignore-file\n" + textwrap.dedent(source), "RL405") == []
    assert python("# ramplint: ignore-file RL405\n" + textwrap.dedent(source), "RL405") == []
    assert len(python("# ramplint: ignore-file RL101\n" + textwrap.dedent(source), "RL405")) == 1


def test_python_syntax_error():
    assert python("class F(:\n") == []


def test_is_forms_module():
    assert is_forms_module(Path("shop/forms.py"))
    assert is_forms_module(Path("shop/forms/checkout.py"))
    assert not is_forms_module(Path("shop/views.py"))
    assert not is_forms_module(Path("shop/forms.html"))


def test_template_rules_skip_python_and_back(tmp_path):
    path = tmp_path / "forms.py"
    path.write_text('class F(forms.Form):\n    a = forms.CharField(label="")\n')
    assert [v.code for v in lint_file(path)] == ["RL405"]
    page = tmp_path / "page.html"
    page.write_text("<img src=x>")
    assert [v.code for v in lint_file(page)] == ["RL101"]


def test_forms_modules_are_linted_in_projects(tmp_path):
    root = tmp_path
    (root / "manage.py").write_text(
        'import os\nos.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf")\n'
    )
    (root / "conf.py").write_text(
        'TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", '
        '"DIRS": ["templates"]}]\n'
    )
    for name in ("templates/widgets", "shop/forms", "node_modules/pkg", ".venv/lib"):
        (root / name).mkdir(parents=True)
    (root / "templates/widgets/w.html").write_text('<input name="{{ widget.name }}">')
    (root / "shop/forms.py").write_text(
        "class W(forms.Widget):\n    template_name = 'widgets/w.html'\n"
    )
    (root / "shop/forms/extra.py").write_text("")
    (root / "shop/views.py").write_text("")
    (root / "node_modules/pkg/forms.py").write_text("")
    (root / ".venv/lib/forms.py").write_text("")
    workspace = Workspace((".html",), cwd=root, environ={})
    found = sorted(p.as_posix() for p in workspace.files(None))
    assert found == ["shop/forms.py", "shop/forms/extra.py", "templates/widgets/w.html"]
    index = workspace.python_index(root / "shop/forms.py")
    assert [v.code for v in lint_file(root / "shop/forms.py", index=index)] == ["RL406"]
    assert workspace.python_index(tmp_path.parent / "elsewhere.py") is None
    assert sorted(
        p.as_posix() for p in Workspace((".html",), cwd=root, environ={}, forms=False).files(None)
    ) == ["templates/widgets/w.html"]


def test_dynamic_field_names():
    source = (
        "class F(forms.Form):\n"
        "    def __init__(self):\n"
        '        self.fields[f"price_{pk}"] = forms.DecimalField(label="")\n'
        '        self.fields[NAME] = forms.DecimalField(label="")\n'
    )
    found = lint_python_source(source, "forms.py", rules=select_rules(["RL405"]))
    assert [v.message.split(" has")[0] for v in found] == ['Field "price_{pk}"', 'Field "NAME"']
