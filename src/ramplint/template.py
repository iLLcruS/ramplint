"""Template preprocessing.

Django and Jinja2 template syntax is not HTML, so before parsing we replace
every template token with something an HTML parser can digest while keeping
the exact line and column of everything else:

* ``{{ variable }}`` and text-producing tags such as ``{% trans %}`` or
  ``{% url %}`` become :data:`TEXT` - "some text will be here at runtime".
* Tags that may render arbitrary markup (``{% include %}``, ``{% block %}``,
  custom template tags) and variables that render HTML (form fields such as
  ``{{ form.email }}``, ``{{ form.as_p }}``, ``{{ html|safe }}``) become
  :data:`MARKUP` - "unknown HTML will be here".
* Control-flow tags (``{% if %}``, ``{% for %}``, ...) and comments become
  plain whitespace.

Each replacement has the same length as the original token and keeps its
newlines, so reported positions always point at the real template source.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

#: Placeholder for text that only exists at render time.
TEXT = ""
#: Placeholder for markup that only exists at render time.
MARKUP = ""
#: ``{% block %}`` of a child template (one with ``{% extends %}``): it renders
#: the content written right after it, so it only hides markup if a template
#: that extends this one overrides it.
CHILD_BLOCK = ""
PLACEHOLDERS = (TEXT, MARKUP, CHILD_BLOCK)


def may_render_markup(text: str) -> bool:
    """``text`` contains a template tag or variable that may render HTML."""
    return MARKUP in text or CHILD_BLOCK in text


_COMMENT_BLOCK_RE = re.compile(r"\{%-?\s*comment\b.*?%\}.*?\{%-?\s*endcomment\s*-?%\}", re.DOTALL)
_TOKEN_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
_TAG_NAME_RE = re.compile(r"\{%-?\s*(\w+)")
_EXTENDS_RE = re.compile(r"\{%-?\s*extends\b")
_SUPPRESS_RE = re.compile(
    r"(?:\{#|<!--)\s*ramplint:\s*(ignore-file|ignore)\b(.*?)(?:#\}|-->)", re.DOTALL
)
_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*")

# Tags that never produce output themselves.
# fmt: off
SILENT_TAGS = frozenset(
    {
        # Django
        "if", "elif", "else", "endif", "for", "empty", "endfor", "with",
        "endwith", "endblock", "extends", "load", "comment", "endcomment",
        "spaceless", "endspaceless", "autoescape", "endautoescape", "verbatim",
        "endverbatim", "blocktrans", "blocktranslate", "endblocktrans",
        "endblocktranslate", "plural", "ifchanged", "endifchanged", "filter",
        "endfilter", "regroup", "resetcycle", "csrf_token", "localize",
        "endlocalize", "localtime", "endlocaltime", "timezone", "endtimezone",
        "get_current_language", "get_current_language_bidi",
        "get_available_languages", "get_language_info",
        "get_language_info_list", "language", "endlanguage", "debug",
        # Jinja2
        "set", "endset", "macro", "endmacro", "call", "endcall", "raw",
        "endraw", "import", "from", "do", "trans_end",
    }
)
# fmt: on

# Tags that render plain text (never markup).
# fmt: off
TEXT_TAGS = frozenset(
    {
        "trans", "translate", "url", "static", "now", "firstof", "cycle",
        "widthratio", "lorem", "templatetag", "get_static_prefix",
        "get_media_prefix", "querystring",
    }
)
# fmt: on


# Variables that render HTML rather than text: forms, form fields and
# anything marked safe.
_FORM_NAME_RE = re.compile(r"^(\w+_)?(form|formset)$|^(bound_)?field$")
#: Form/field attributes that render markup.
_FORM_MARKUP_ATTRS = frozenset(
    {
        "as_p", "as_table", "as_ul", "as_div", "as_field_group", "as_widget",
        "label_tag", "legend_tag", "errors", "non_field_errors", "management_form",
        "media", "empty_form",
    }
)  # fmt: skip
_MARKUP_FILTERS = frozenset({"safe", "safeseq", "as_crispy_field", "crispy", "as_crispy_errors"})


def _renders_markup(token: str) -> bool:
    """``{{ form.email }}``, ``{{ form.as_p }}``, ``{{ body|safe }}``, ..."""
    expression = token[2:-2].strip("- \t\n")
    variable, *filters = (part.strip() for part in expression.split("|"))
    if any(f.split(":")[0].strip() in _MARKUP_FILTERS for f in filters):
        return True
    names = variable.split(".")
    if not all(re.fullmatch(r"\w+", name) for name in names):
        return False
    if names[-1] in _FORM_MARKUP_ATTRS or names == ["block", "super"]:
        return True
    # form, field, form.email, form.fields.email, user_form.email ...
    if not _FORM_NAME_RE.match(names[0]):
        return False
    return len(names) == 1 or (len(names) == 2 and names[0] != "field")


@dataclass
class Suppressions:
    """Inline ``ramplint: ignore`` directives found in a template."""

    whole_file: set[str] | None = None
    by_line: dict[int, set[str]] = field(default_factory=dict)

    def is_suppressed(self, line: int, code: str, name: str) -> bool:
        for scope in (self.whole_file, self.by_line.get(line)):
            if scope is None:
                continue
            if not scope or code in scope or name in scope:
                return True
        return False


#: Position inside conditional template blocks: one ``(block_id, branch_index)``
#: pair per enclosing ``{% if %}`` / ``{% for %}`` / ``{% ifchanged %}``.
BranchPath = tuple[tuple[int, int], ...]

_BLOCK_OPENERS = {"if": "if", "ifchanged": "ifchanged", "for": "for"}
_BLOCK_CLOSERS = {"endif": "if", "endifchanged": "ifchanged", "endfor": "for"}
_BLOCK_SPLITTERS = frozenset({"elif", "else", "empty"})


@dataclass
class BranchMap:
    """Maps a source position to the template branch it belongs to."""

    line_starts: list[int]
    offsets: list[int] = field(default_factory=lambda: [0])
    paths: list[BranchPath] = field(default_factory=lambda: [()])

    def at(self, line: int, col: int) -> BranchPath:
        if not 1 <= line <= len(self.line_starts):
            return ()
        offset = self.line_starts[line - 1] + col - 1
        return self.paths[bisect_right(self.offsets, offset) - 1]


def mutually_exclusive(a: BranchPath, b: BranchPath) -> bool:
    """True if two positions can never be rendered together.

    That is the case when they sit in different branches of the same
    ``{% if %}`` / ``{% elif %}`` / ``{% else %}`` (or ``{% for %}`` /
    ``{% empty %}``) block.
    """
    for (block_a, branch_a), (block_b, branch_b) in zip(a, b, strict=False):
        if block_a != block_b:
            return False
        if branch_a != branch_b:
            return True
    return False


def _build_branch_map(source: str) -> BranchMap:
    line_starts = [0]
    for index, char in enumerate(source):
        if char == "\n":
            line_starts.append(index + 1)
    branch_map = BranchMap(line_starts=line_starts)

    stack: list[list] = []  # [block_id, branch_index, kind]
    next_block_id = 0
    for match in _TOKEN_RE.finditer(source):
        name_match = _TAG_NAME_RE.match(match.group(0))
        if not name_match:
            continue
        name = name_match.group(1)
        if name in _BLOCK_OPENERS:
            next_block_id += 1
            stack.append([next_block_id, 0, _BLOCK_OPENERS[name]])
        elif name in _BLOCK_SPLITTERS and stack:
            stack[-1][1] += 1
        elif name in _BLOCK_CLOSERS:
            kind = _BLOCK_CLOSERS[name]
            for index in range(len(stack) - 1, -1, -1):
                if stack[index][2] == kind:
                    del stack[index:]
                    break
            else:
                continue  # stray closing tag in a fragment
        else:
            continue
        branch_map.offsets.append(match.end())
        branch_map.paths.append(tuple((block, branch) for block, branch, _ in stack))
    return branch_map


@dataclass
class PreparedTemplate:
    html: str
    suppressions: Suppressions
    branches: BranchMap


def _blank(token: str) -> str:
    return re.sub(r"[^\n]", " ", token)


def _placeholder(marker: str, token: str) -> str:
    return marker + _blank(token[1:])


def _replace_token(match: re.Match[str], child_template: bool = False) -> str:
    token = match.group(0)
    if token.startswith("{#"):
        return _blank(token)
    if token.startswith("{{"):
        return _placeholder(MARKUP if _renders_markup(token) else TEXT, token)
    name_match = _TAG_NAME_RE.match(token)
    name = name_match.group(1) if name_match else ""
    if name in SILENT_TAGS:
        return _blank(token)
    if name in TEXT_TAGS:
        return _placeholder(TEXT, token)
    if name == "block" and child_template:
        return _placeholder(CHILD_BLOCK, token)
    return _placeholder(MARKUP, token)


def _parse_suppressions(source: str) -> Suppressions:
    result = Suppressions()
    for match in _SUPPRESS_RE.finditer(source):
        kind, rest = match.group(1), match.group(2)
        codes = {c for c in _CODE_RE.findall(rest)}
        if kind == "ignore-file":
            # ``None`` = no directive, empty set = every rule.
            if not codes:
                result.whole_file = set()
            elif result.whole_file is None:
                result.whole_file = codes
            elif result.whole_file:
                result.whole_file |= codes
            continue
        start_line = source.count("\n", 0, match.start()) + 1
        end_line = start_line + match.group(0).count("\n")
        # A directive covers its own line(s) and the line right after it.
        for line in range(start_line, end_line + 2):
            current = result.by_line.get(line)
            if current is None:
                result.by_line[line] = set(codes)
            elif current and codes:
                current |= codes
            else:
                result.by_line[line] = set()
    return result


def prepare(source: str) -> PreparedTemplate:
    """Turn template source into parseable HTML of identical geometry."""
    suppressions = _parse_suppressions(source)
    without_comments = _COMMENT_BLOCK_RE.sub(lambda m: _blank(m.group(0)), source)
    branches = _build_branch_map(without_comments)
    child_template = _EXTENDS_RE.search(without_comments) is not None
    html = _TOKEN_RE.sub(lambda m: _replace_token(m, child_template), without_comments)
    return PreparedTemplate(html=html, suppressions=suppressions, branches=branches)
