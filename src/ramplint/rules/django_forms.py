"""Checks of Django form classes and widgets in ``forms.py`` (RL405, RL406)."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

from ramplint.pyforms import PythonModule, dict_keys, keyword, name_of, string_value
from ramplint.rules.base import python_rule

#: Attributes that give an input a name without a <label>.
_NAMING_ATTRS = frozenset({"aria-label", "aria-labelledby", "title"})


def _is_form_class(node: ast.ClassDef) -> bool:
    return any(name_of(base).endswith("Form") for base in node.bases)


def _widget_call(field: ast.Call) -> ast.Call | None:
    widget = keyword(field, "widget")
    return widget.value if widget is not None and isinstance(widget.value, ast.Call) else None


def _is_hidden(widget: ast.AST | None) -> bool:
    return widget is not None and "Hidden" in name_of(widget)


def _attrs(widget: ast.Call | None) -> set[str]:
    if widget is None:
        return set()
    attrs = keyword(widget, "attrs")
    return dict_keys(attrs.value if attrs is not None else None)


def _empty_label_message(field_name: str, attrs: set[str]) -> str:
    hint = " (a placeholder is not a label)" if "placeholder" in attrs else ""
    return (
        f'Field "{field_name}" has an empty label, so it renders <label></label> and screen '
        f"readers announce the input without a name{hint}; give it a label (hide it "
        "visually in the template if needed) or an aria-label in the widget attrs"
    )


def _meta_dict(cls: ast.ClassDef, name: str) -> ast.Dict | None:
    meta = next((n for n in cls.body if isinstance(n, ast.ClassDef) and n.name == "Meta"), None)
    if meta is None:
        return None
    for statement in meta.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in statement.targets
        ):
            return statement.value if isinstance(statement.value, ast.Dict) else None
    return None


def _meta_widget_attrs(cls: ast.ClassDef) -> dict[str, set[str]]:
    widgets = _meta_dict(cls, "widgets")
    result: dict[str, set[str]] = {}
    if widgets is None:
        return result
    for key, value in zip(widgets.keys, widgets.values, strict=True):
        if isinstance(key, ast.Constant) and isinstance(value, ast.Call):
            result[key.value] = _attrs(value) | ({"#hidden"} if _is_hidden(value) else set())
    return result


def _key_text(node: ast.expr) -> str:
    """``"email"`` -> email, ``f"price_{pk}"`` -> price_{pk}."""
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.JoinedStr):
        return "".join(
            str(part.value)
            if isinstance(part, ast.Constant)
            else "{" + ast.unparse(part.value) + "}"  # type: ignore[attr-defined]
            for part in node.values
        )
    return ast.unparse(node)


def _dynamic_field(node: ast.Assign) -> Iterator[tuple[int, int, str]]:
    call = node.value
    assert isinstance(call, ast.Call)
    label = keyword(call, "label")
    text = string_value(label.value) if label is not None else None
    if label is None or text is None or text.strip():
        return
    widget = keyword(call, "widget")
    attrs = _attrs(
        widget.value if widget is not None and isinstance(widget.value, ast.Call) else None
    )
    if (widget is not None and _is_hidden(widget.value)) or attrs & _NAMING_ATTRS:
        return
    for target in node.targets:
        if isinstance(target, ast.Subscript) and name_of(target.value) == "fields":
            name = _key_text(target.slice)
            yield (
                label.value.lineno,
                label.value.col_offset + 1,
                _empty_label_message(str(name), attrs),
            )


@python_rule(
    code="RL405",
    name="form-label-empty",
    summary="Django form fields must not have an empty label.",
    wcag="1.3.1 Info and Relationships (A), 4.1.2 Name, Role, Value (A)",
)
def form_label_empty(module: PythonModule) -> Iterator[tuple[int, int, str]]:
    for cls in module.classes():
        if not _is_form_class(cls):
            continue
        meta_widgets = _meta_widget_attrs(cls)
        # email = forms.EmailField(label="", widget=...)
        for statement in cls.body:
            if not (isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call)):
                continue
            call = statement.value
            if not name_of(call.func).endswith("Field"):
                continue
            label = keyword(call, "label")
            text = string_value(label.value) if label is not None else None
            if label is None or text is None or text.strip():
                continue
            widget = _widget_call(call)
            attrs = _attrs(widget)
            widget_keyword = keyword(call, "widget")
            if (widget_keyword and _is_hidden(widget_keyword.value)) or attrs & _NAMING_ATTRS:
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    yield (
                        label.value.lineno,
                        label.value.col_offset + 1,
                        _empty_label_message(target.id, attrs),
                    )
        # class Meta: labels = {"email": ""}
        labels = _meta_dict(cls, "labels")
        if labels is not None:
            for key, value in zip(labels.keys, labels.values, strict=True):
                text = string_value(value)
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if text is None or text.strip():
                    continue
                attrs = meta_widgets.get(key.value, set())
                if "#hidden" in attrs or attrs & _NAMING_ATTRS:
                    continue
                yield value.lineno, value.col_offset + 1, _empty_label_message(key.value, attrs)
        # self.fields["email"].label = "" / self.fields[name] = forms.CharField(label="")
        for node in ast.walk(cls):
            if not isinstance(node, ast.Assign):
                continue
            if isinstance(node.value, ast.Call) and name_of(node.value.func).endswith("Field"):
                yield from _dynamic_field(node)
                continue
            text = string_value(node.value)
            if text is None or text.strip():
                continue
            for target in node.targets:
                if not (isinstance(target, ast.Attribute) and target.attr == "label"):
                    continue
                owner = target.value
                if (
                    isinstance(owner, ast.Subscript)
                    and name_of(owner.value) == "fields"
                    and isinstance(owner.slice, ast.Constant)
                ):
                    yield (
                        node.value.lineno,
                        node.value.col_offset + 1,
                        _empty_label_message(str(owner.slice.value), set()),
                    )


# --------------------------------------------------------------------------
# RL406 widget-id
# --------------------------------------------------------------------------

_WIDGET_BASES = ("Widget", "Input", "Select", "Textarea", "SelectMultiple", "RadioSelect")
_TEMPLATE_KEEPS_ATTRS_RE = re.compile(
    r"widget\.attrs|attrs\.html|widget\.subwidgets|\{%-?\s*extends\b"
)
_INTERACTIVE_RE = re.compile(r"<(input|select|textarea|button)\b|contenteditable|\brole=", re.I)


def _is_widget_class(node: ast.ClassDef) -> bool:
    return any(name_of(base).endswith(_WIDGET_BASES) for base in node.bases)


def _always_empty(function: ast.FunctionDef) -> bool:
    """The body is a single ``return None`` / ``return ""`` / ``return``."""
    body = [
        s
        for s in function.body
        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
    ]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    value = body[0].value
    return value is None or (isinstance(value, ast.Constant) and value.value in (None, ""))


@python_rule(
    code="RL406",
    name="widget-id",
    summary="Custom Django widgets must keep the id that labels point to.",
    wcag="1.3.1 Info and Relationships (A), 4.1.2 Name, Role, Value (A)",
)
def widget_id(module: PythonModule) -> Iterator[tuple[int, int, str]]:
    for cls in module.classes():
        if not _is_widget_class(cls):
            continue
        for statement in cls.body:
            if isinstance(statement, ast.FunctionDef) and statement.name == "id_for_label":
                if _always_empty(statement):
                    yield (
                        statement.lineno,
                        statement.col_offset + 1,
                        f"{cls.name}.id_for_label() returns nothing, so <label for> and "
                        "aria-describedby have no element to point to; return the id of the "
                        "element that receives focus",
                    )
            elif isinstance(statement, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "template_name" for t in statement.targets
            ):
                name = string_value(statement.value)
                if name is None or module.index is None:
                    continue
                template = module.index.get(name)
                if template is None:
                    continue
                source = template.source
                if _TEMPLATE_KEEPS_ATTRS_RE.search(source) or not _INTERACTIVE_RE.search(source):
                    continue
                yield (
                    statement.value.lineno,
                    statement.value.col_offset + 1,
                    f'Widget template "{name}" never renders widget.attrs, so the input gets '
                    "no id: <label for> and aria-describedby point to nothing. Add "
                    '{% include "django/forms/widgets/attrs.html" %} to the input',
                )
