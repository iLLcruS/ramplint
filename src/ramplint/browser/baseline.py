"""``--baseline scan.json``: report only the problems that are new.

Turning on a browser scan for an existing site shows hundreds of old problems.
With a baseline, every finding is ``new``, ``existing`` or ``fixed``, and only
new ones fail the run, so a team can fix the old ones over time.

Findings are matched by a fingerprint that survives unrelated changes: the
rule, where the element comes from (its template, or its URL pattern) and its
selector without ``:nth-of-type()`` indices, and the message with numbers
blanked out. Line numbers are not part of it, so moving an element inside a
template keeps its finding ``existing``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import urlsplit

from ramplint.browser.urls import url_pattern
from ramplint.linter import Violation

NEW = "new"
EXISTING = "existing"
FIXED = "fixed"

_INDEX_RE = re.compile(r":nth-(?:of-type|child)\(\d+\)")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_HOST_RE = re.compile(r"https?://[^/\s]+")
_SPACE_RE = re.compile(r"\s+")


class BaselineError(Exception):
    """The baseline file cannot be used."""


def _normalized_message(message: str) -> str:
    text = _HOST_RE.sub("", message.lower())
    text = _NUMBER_RE.sub("N", text)
    return _SPACE_RE.sub(" ", text).strip()


def fingerprint(v: Violation) -> str:
    """A short, stable identity of a problem (see the module docs)."""
    location = v.template_location
    if location is not None:
        where = f"template:{location[0]}"
    elif v.in_browser:
        where = "page:" + (urlsplit(url_pattern(v.url or v.path)).path or "/")
    else:
        where = f"file:{v.path}"
    selector = _INDEX_RE.sub("", v.selector or "")
    parts = (v.code, where, selector, _normalized_message(v.message), v.state or "")
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class Comparison:
    #: Current findings, each with ``baseline`` set to ``new`` or ``existing``.
    violations: list[Violation]
    #: Findings of the baseline that are gone (their ``scan.json`` entries).
    fixed: list[dict[str, object]] = field(default_factory=list)

    @property
    def new(self) -> list[Violation]:
        return [v for v in self.violations if v.baseline == NEW]

    @property
    def existing(self) -> list[Violation]:
        return [v for v in self.violations if v.baseline == EXISTING]


def load_baseline(path: Path) -> list[dict[str, object]]:
    """The findings stored in a ``scan.json`` (``--format html -o`` or ``--write-baseline``)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BaselineError(f"cannot read baseline {path}: {exc.strerror or exc}") from None
    except ValueError:
        raise BaselineError(f"baseline {path} is not a ramplint scan.json") from None
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise BaselineError(f"baseline {path} is not a ramplint scan.json (schema 1)")
    findings = data.get("violations")
    if not isinstance(findings, list) or not all(
        isinstance(f, dict) and isinstance(f.get("fingerprint"), str) for f in findings
    ):
        raise BaselineError(f"baseline {path} has no fingerprinted findings")
    return findings


def compare(violations: Sequence[Violation], baseline: Sequence[dict[str, object]]) -> Comparison:
    """Mark each finding ``new`` or ``existing``; list the baseline's ``fixed`` ones."""
    remaining = Counter(str(entry["fingerprint"]) for entry in baseline)
    marked = []
    for v in violations:
        key = fingerprint(v)
        if remaining[key] > 0:
            remaining[key] -= 1
            marked.append(replace(v, baseline=EXISTING))
        else:
            marked.append(replace(v, baseline=NEW))
    fixed = []
    for entry in baseline:
        key = str(entry["fingerprint"])
        if remaining[key] > 0:
            remaining[key] -= 1
            fixed.append(entry)
    return Comparison(marked, fixed)
