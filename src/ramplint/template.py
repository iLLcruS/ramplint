"""Template preprocessing.

Django and Jinja2 template syntax is not HTML, so before parsing we replace
every template token with something an HTML parser can digest while keeping
the exact line and column of everything else:

* ``{{ variable }}`` and text-producing tags such as ``{% trans %}`` or
  ``{% url %}`` become :data:`TEXT` - "some text will be here at runtime".
* Tags that may render arbitrary markup (``{% include %}``, ``{% block %}``,
  custom template tags) become :data:`MARKUP` - "unknown HTML will be here".
* Control-flow tags (``{% if %}``, ``{% for %}``, ...) and comments become
  plain whitespace.

Each replacement has the same length as the original token and keeps its
newlines, so reported positions always point at the real template source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Placeholder for text that only exists at render time.
TEXT = ""
#: Placeholder for markup that only exists at render time.
MARKUP = ""
PLACEHOLDERS = (TEXT, MARKUP)

_COMMENT_BLOCK_RE = re.compile(r"\{%-?\s*comment\b.*?%\}.*?\{%-?\s*endcomment\s*-?%\}", re.DOTALL)
_TOKEN_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
_TAG_NAME_RE = re.compile(r"\{%-?\s*(\w+)")
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


@dataclass
class PreparedTemplate:
    html: str
    suppressions: Suppressions


def _blank(token: str) -> str:
    return re.sub(r"[^\n]", " ", token)


def _placeholder(marker: str, token: str) -> str:
    return marker + _blank(token[1:])


def _replace_token(match: re.Match[str]) -> str:
    token = match.group(0)
    if token.startswith("{#"):
        return _blank(token)
    if token.startswith("{{"):
        return _placeholder(TEXT, token)
    name_match = _TAG_NAME_RE.match(token)
    name = name_match.group(1) if name_match else ""
    if name in SILENT_TAGS:
        return _blank(token)
    if name in TEXT_TAGS:
        return _placeholder(TEXT, token)
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
    html = _COMMENT_BLOCK_RE.sub(lambda m: _blank(m.group(0)), source)
    html = _TOKEN_RE.sub(_replace_token, html)
    return PreparedTemplate(html=html, suppressions=suppressions)
