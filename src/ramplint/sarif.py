"""SARIF 2.1.0 output (``--format sarif``) for GitHub Code Scanning.

Upload the file with ``github/codeql-action/upload-sarif`` and problems show
up in the repository's Security tab and as pull request annotations.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO
from urllib.parse import quote

from ramplint import __version__
from ramplint.linter import Violation
from ramplint.reporters import reporter
from ramplint.rules import all_rules

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
INFORMATION_URI = "https://github.com/iLLcruS/ramplint"


def _artifact_uri(path: str) -> str:
    """Repository-relative URI; Code Scanning matches results to files by it."""
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = Path(os.path.relpath(candidate))
        except ValueError:  # another drive on Windows
            return candidate.as_uri()
    return quote(candidate.as_posix())


def _rule_descriptors() -> list[dict[str, object]]:
    descriptors = []
    for rule in all_rules():
        help_text = f"{rule.summary} WCAG {rule.wcag}. See {rule.docs_url}"
        descriptors.append(
            {
                "id": rule.code,
                "name": rule.name,
                "shortDescription": {"text": rule.summary},
                "fullDescription": {"text": f"{rule.summary} WCAG {rule.wcag}."},
                "helpUri": rule.docs_url,
                "help": {
                    "text": help_text,
                    "markdown": (
                        f"**{rule.code} {rule.name}**: {rule.summary}\n\n"
                        f"WCAG {rule.wcag}\n\n[Documentation]({rule.docs_url})"
                    ),
                },
                "defaultConfiguration": {"level": "error"},
                "properties": {
                    "tags": ["accessibility", "a11y", "wcag"],
                    "precision": "high",
                    "problem.severity": "error",
                },
            }
        )
    return descriptors


@reporter("sarif", "SARIF 2.1.0 for GitHub Code Scanning and other SAST dashboards")
def report_sarif(
    violations: Sequence[Violation], files_checked: int, out: TextIO, color: bool = False
) -> None:
    rules = _rule_descriptors()
    rule_index = {descriptor["id"]: index for index, descriptor in enumerate(rules)}
    results = [
        {
            "ruleId": v.code,
            **({"ruleIndex": rule_index[v.code]} if v.code in rule_index else {}),
            "level": "error",
            "message": {"text": v.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": _artifact_uri(v.path)},
                        "region": {"startLine": v.line, "startColumn": v.col},
                    }
                }
            ],
        }
        for v in violations
    ]
    sarif = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ramplint",
                        "version": __version__,
                        "semanticVersion": __version__,
                        "informationUri": INFORMATION_URI,
                        "rules": rules,
                    }
                },
                "columnKind": "unicodeCodePoints",
                "results": results,
                "properties": {"filesChecked": files_checked},
            }
        ],
    }
    json.dump(sarif, out, indent=2)
    out.write("\n")
