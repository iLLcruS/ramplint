"""WAI-ARIA reference data (WAI-ARIA 1.2, plus Graphics ARIA, DPUB-ARIA and
roles added in ARIA 1.3 so that modern markup is not reported)."""

from __future__ import annotations

# fmt: off
ROLES = frozenset({
    "alert", "alertdialog", "application", "article", "banner", "blockquote",
    "button", "caption", "cell", "checkbox", "code", "columnheader", "combobox",
    "comment", "complementary", "contentinfo", "definition", "deletion", "dialog",
    "directory", "document", "emphasis", "feed", "figure", "form", "generic",
    "grid", "gridcell", "group", "heading", "image", "img", "insertion", "link",
    "list", "listbox", "listitem", "log", "main", "mark", "marquee", "math",
    "menu", "menubar", "menuitem", "menuitemcheckbox", "menuitemradio", "meter",
    "navigation", "none", "note", "option", "paragraph", "presentation",
    "progressbar", "radio", "radiogroup", "region", "row", "rowgroup",
    "rowheader", "scrollbar", "search", "searchbox", "separator", "slider",
    "spinbutton", "status", "strong", "subscript", "suggestion", "superscript",
    "switch", "tab", "table", "tablist", "tabpanel", "term", "textbox", "time",
    "timer", "toolbar", "tooltip", "tree", "treegrid", "treeitem",
    # Graphics ARIA
    "graphics-document", "graphics-object", "graphics-symbol",
    # DPUB-ARIA
    "doc-abstract", "doc-acknowledgments", "doc-afterword", "doc-appendix",
    "doc-backlink", "doc-biblioentry", "doc-bibliography", "doc-biblioref",
    "doc-chapter", "doc-colophon", "doc-conclusion", "doc-cover", "doc-credit",
    "doc-credits", "doc-dedication", "doc-endnote", "doc-endnotes", "doc-epigraph",
    "doc-epilogue", "doc-errata", "doc-example", "doc-footnote", "doc-foreword",
    "doc-glossary", "doc-glossref", "doc-index", "doc-introduction", "doc-noteref",
    "doc-notice", "doc-pagebreak", "doc-pagefooter", "doc-pageheader",
    "doc-pagelist", "doc-part", "doc-preface", "doc-prologue", "doc-pullquote",
    "doc-qna", "doc-subtitle", "doc-tip", "doc-toc",
})

#: Roles that exist only to organise the specification.
ABSTRACT_ROLES = frozenset({
    "command", "composite", "input", "landmark", "range", "roletype", "section",
    "sectionhead", "select", "structure", "widget", "window",
})

ATTRIBUTES = frozenset({
    "aria-activedescendant", "aria-atomic", "aria-autocomplete", "aria-braillelabel",
    "aria-brailleroledescription", "aria-busy", "aria-checked", "aria-colcount",
    "aria-colindex", "aria-colindextext", "aria-colspan", "aria-controls",
    "aria-current", "aria-describedby", "aria-description", "aria-details",
    "aria-disabled", "aria-dropeffect", "aria-errormessage", "aria-expanded",
    "aria-flowto", "aria-grabbed", "aria-haspopup", "aria-hidden", "aria-invalid",
    "aria-keyshortcuts", "aria-label", "aria-labelledby", "aria-level", "aria-live",
    "aria-modal", "aria-multiline", "aria-multiselectable", "aria-orientation",
    "aria-owns", "aria-placeholder", "aria-posinset", "aria-pressed",
    "aria-readonly", "aria-relevant", "aria-required", "aria-roledescription",
    "aria-rowcount", "aria-rowindex", "aria-rowindextext", "aria-rowspan",
    "aria-selected", "aria-setsize", "aria-sort", "aria-valuemax", "aria-valuemin",
    "aria-valuenow", "aria-valuetext",
})
# fmt: on

TRUE_FALSE = frozenset({"true", "false"})
TRUE_FALSE_UNDEFINED = frozenset({"true", "false", "undefined"})
TRISTATE = frozenset({"true", "false", "mixed", "undefined"})

#: Attribute -> allowed values (single token).
TOKEN_VALUES: dict[str, frozenset[str]] = {
    "aria-atomic": TRUE_FALSE,
    "aria-busy": TRUE_FALSE,
    "aria-disabled": TRUE_FALSE,
    "aria-modal": TRUE_FALSE,
    "aria-multiline": TRUE_FALSE,
    "aria-multiselectable": TRUE_FALSE,
    "aria-readonly": TRUE_FALSE,
    "aria-required": TRUE_FALSE,
    "aria-hidden": TRUE_FALSE_UNDEFINED,
    "aria-expanded": TRUE_FALSE_UNDEFINED,
    "aria-selected": TRUE_FALSE_UNDEFINED,
    "aria-grabbed": TRUE_FALSE_UNDEFINED,
    "aria-checked": TRISTATE,
    "aria-pressed": TRISTATE,
    "aria-autocomplete": frozenset({"inline", "list", "both", "none"}),
    "aria-current": frozenset({"page", "step", "location", "date", "time", "true", "false"}),
    "aria-haspopup": frozenset({"false", "true", "menu", "listbox", "tree", "grid", "dialog"}),
    "aria-invalid": frozenset({"grammar", "false", "spelling", "true"}),
    "aria-live": frozenset({"assertive", "off", "polite"}),
    "aria-orientation": frozenset({"horizontal", "vertical", "undefined"}),
    "aria-sort": frozenset({"ascending", "descending", "none", "other"}),
}

#: Attribute -> allowed tokens of a space-separated list.
TOKEN_LIST_VALUES: dict[str, frozenset[str]] = {
    "aria-relevant": frozenset({"additions", "removals", "text", "all"}),
    "aria-dropeffect": frozenset({"copy", "execute", "link", "move", "none", "popup"}),
}

#: Attribute -> minimum integer value.
INTEGER_VALUES: dict[str, int] = {
    "aria-level": 1,
    "aria-posinset": 1,
    "aria-colspan": 1,
    "aria-rowspan": 0,
    "aria-colindex": 1,
    "aria-rowindex": 1,
    "aria-setsize": -1,
    "aria-colcount": -1,
    "aria-rowcount": -1,
}

NUMBER_VALUES = frozenset({"aria-valuenow", "aria-valuemin", "aria-valuemax"})

#: Attributes that reference other elements by id.
ID_REFERENCES = frozenset({"aria-labelledby", "aria-describedby"})
ID_REFERENCE_LISTS = frozenset(
    {
        "aria-labelledby",
        "aria-describedby",
        "aria-controls",
        "aria-owns",
        "aria-flowto",
        "aria-details",
        "aria-errormessage",
        "aria-activedescendant",
    }
)

#: Role -> attributes it requires (WAI-ARIA 1.2).
REQUIRED_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "checkbox": ("aria-checked",),
    "radio": ("aria-checked",),
    "switch": ("aria-checked",),
    "menuitemcheckbox": ("aria-checked",),
    "menuitemradio": ("aria-checked",),
    "combobox": ("aria-expanded",),
    "heading": ("aria-level",),
    "slider": ("aria-valuenow",),
    "scrollbar": ("aria-controls", "aria-valuenow"),
}
