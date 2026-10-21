from __future__ import annotations

import re
from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules import lang_data
from ramplint.rules.base import rule
from ramplint.template import PLACEHOLDERS, may_render_markup


@rule(
    code="RL601",
    name="html-lang",
    summary="The <html> element must declare the page language.",
    wcag="3.1.1 Language of Page (A)",
)
def html_lang(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("html"):
        if node.dynamic_attrs or node.has_value("lang"):
            continue
        yield (
            node,
            (
                '<html> is missing a lang attribute; add e.g. lang="en" or '
                'lang="{{ LANGUAGE_CODE }}"'
            ),
        )


_VIEWPORT_SPLIT_RE = re.compile(r"[,;]")
_DISABLED_SCALING = frozenset({"no", "0", "false"})
#: WCAG 1.4.4 requires text to be resizable up to 200 %.
_MIN_MAXIMUM_SCALE = 2.0


def _viewport_settings(content: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    for part in _VIEWPORT_SPLIT_RE.split(content):
        key, sep, value = part.partition("=")
        if sep:
            settings[key.strip().lower()] = value.strip().lower()
    return settings


@rule(
    code="RL602",
    name="viewport-zoom",
    summary="The viewport meta tag must not disable zooming.",
    wcag="1.4.4 Resize Text (AA)",
)
def viewport_zoom(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("meta"):
        if (node.get("name") or "").strip().lower() != "viewport":
            continue
        settings = _viewport_settings(node.get("content") or "")
        problems: list[str] = []

        scalable = settings.get("user-scalable")
        if scalable is not None and scalable in _DISABLED_SCALING:
            problems.append(f"user-scalable={scalable} disables zooming")

        maximum = settings.get("maximum-scale")
        if maximum is not None and not any(p in maximum for p in PLACEHOLDERS):
            try:
                # Zero or negative values are invalid and ignored by browsers.
                if 0 < float(maximum) < _MIN_MAXIMUM_SCALE:
                    problems.append(f"maximum-scale={maximum} limits zoom below 200%")
            except ValueError:
                pass

        if problems:
            yield (
                node,
                f"Viewport meta tag: {'; '.join(problems)}. Users must be able to "
                "zoom; remove these settings",
            )


# --------------------------------------------------------------------------
# RL603 document-title
# --------------------------------------------------------------------------


def _document_title(html: Node) -> Node | None:
    """The page <title> (a <title> inside <svg> names the graphic instead)."""
    for node in html.iter("title"):
        if not any(ancestor.tag == "svg" for ancestor in node.ancestors()):
            return node
    return None


@rule(
    code="RL603",
    name="document-title",
    summary="Pages must have a non-empty <title>.",
    wcag="2.4.2 Page Titled (A)",
)
def document_title(root: Node) -> Iterator[tuple[Node, str]]:
    html = next(root.iter("html"), None)
    if html is None:
        # A partial or a child template: the parent owns the <title>.
        yield from _empty_title_block(root)
        return
    title = _document_title(html)
    if title is None:
        head = next(html.iter("head"), None)
        if may_render_markup((head or html).text()):
            return  # {% block %} / {% include %} may render the <title>
        yield (
            head or html,
            "Page has no <title>; screen readers announce it first and users see it "
            "in tabs and history. Add e.g. <title>{% block title %}Shop{% endblock %}</title>",
        )
        return
    if title.dynamic_attrs or title.text().strip():
        return
    yield title, "<title> is empty; describe the page, e.g. <title>Orders | Shop</title>"


def _empty_title_block(root: Node) -> Iterator[tuple[Node, str]]:
    context = root.context
    if context is None:
        return
    found = context.empty_title_block()
    if found is None:
        return
    base, name = found
    line, col = context.template.position(context.template.extends.offset)
    yield (
        Node(tag="#extends", attrs={}, line=line, col=col),
        f"The page title stays empty: {base.path.name} renders "
        f"<title>{{% block {name} %}}{{% endblock %}}</title> and nothing fills the "
        f'"{name}" block; add {{% block {name} %}}Orders | Shop{{% endblock %}}',
    )


# --------------------------------------------------------------------------
# RL604 valid-lang
# --------------------------------------------------------------------------

_LANGTAG_RE = re.compile(
    r"""^
    (?P<language>[a-z]{2,8})
    (-[a-z]{3}){0,3}                          # extlang
    (-[a-z]{4})?                              # script
    (-([a-z]{2}|\d{3}))?                      # region
    (-([a-z\d]{5,8}|\d[a-z\d]{3}))*           # variants
    (-[a-wyz\d](-[a-z\d]{2,8})+)*             # extensions
    (-x(-[a-z\d]{1,8})+)?                     # private use
    $""",
    re.VERBOSE,
)
_PRIVATE_OR_GRANDFATHERED_RE = re.compile(r"^(x|i)(-[a-z\d]{1,8})+$")


def _lang_problem(value: str) -> str | None:
    """Why ``value`` is not a usable BCP 47 language tag, or None."""
    tag = value.strip().lower()
    if not tag or _PRIVATE_OR_GRANDFATHERED_RE.match(tag):
        return None
    suggestion = lang_data.SUGGESTIONS.get(tag)
    if suggestion is None and "_" in tag:
        suggestion = value.strip().replace("_", "-")
    match = _LANGTAG_RE.match(tag)
    if match:
        language = match.group("language")
        if len(language) == 3 or language in lang_data.TWO_LETTER_LANGUAGES:
            return None
        suggestion = suggestion or lang_data.SUGGESTIONS.get(language)
    hint = f'; did you mean "{suggestion}"?' if suggestion else ""
    return f"is not a valid language tag (use codes like en, en-GB, ro, uk){hint}"


def _primary_language(value: str) -> str:
    return value.strip().lower().split("-")[0]


@rule(
    code="RL604",
    name="valid-lang",
    summary="lang values must be valid language tags.",
    wcag="3.1.1 Language of Page (A), 3.1.2 Language of Parts (AA)",
)
def valid_lang(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter():
        values: dict[str, str] = {}
        for name in ("lang", "xml:lang"):
            value = node.get(name)
            if value is None or node.is_dynamic(name):
                continue
            problem = _lang_problem(value)
            if problem:
                yield node, f'{name}="{value.strip()}" {problem}'
            elif value.strip():
                values[name] = value
        if len(values) == 2 and len({_primary_language(v) for v in values.values()}) == 2:
            yield (
                node,
                f'lang="{values["lang"].strip()}" and xml:lang="{values["xml:lang"].strip()}" '
                "name different languages; keep them the same or drop xml:lang",
            )


# --------------------------------------------------------------------------
# RL605 meta-refresh
# --------------------------------------------------------------------------

_REFRESH_DELAY_RE = re.compile(r"^\s*(\d+(?:\.\d*)?|\.\d+)\s*$")


@rule(
    code="RL605",
    name="meta-refresh",
    summary="Pages must not refresh or redirect after a delay.",
    wcag="2.2.1 Timing Adjustable (A), 3.2.5 Change on Request (AAA)",
)
def meta_refresh(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("meta"):
        if (node.get("http-equiv") or "").strip().lower() != "refresh":
            continue
        content = node.get("content") or ""
        # Only the delay must be static: the URL is usually built with {% url %}.
        match = _REFRESH_DELAY_RE.match(re.split(r"[;,]", content, maxsplit=1)[0])
        if not match or float(match.group(1)) == 0:
            continue
        delay = match.group(1)
        seconds = f"{delay} second{'' if delay == '1' else 's'}"
        if "url" in content.lower():
            message = (
                f"The page redirects after {seconds}, before some users finish reading; "
                'redirect on the server (or with content="0; url=...") or show a link'
            )
        else:
            message = (
                f"The page reloads every {seconds}, which moves users back to the top; "
                "let them refresh it themselves or update the content with JavaScript"
            )
        yield node, message


# --------------------------------------------------------------------------
# RL606 obsolete-elements
# --------------------------------------------------------------------------


@rule(
    code="RL606",
    name="obsolete-elements",
    summary="<marquee> and <blink> must not be used.",
    wcag="2.2.2 Pause, Stop, Hide (A)",
)
def obsolete_elements(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("marquee", "blink"):
        yield (
            node,
            f"<{node.tag}> moves or flashes content that users cannot pause; use static "
            "text, or an animation with a pause button that respects prefers-reduced-motion",
        )
