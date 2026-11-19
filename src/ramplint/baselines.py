"""``--baseline`` / ``--write-baseline`` for the template linter.

The browser scan has had baselines since 0.7.0 (see
:mod:`ramplint.browser.baseline`). The template linter uses the same file
format (a ``scan.json`` with schema 1) and the same fingerprints, so a team
can turn ramplint on in an existing project, commit the baseline and fail CI
only on problems that are new.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from ramplint import __version__
from ramplint.browser.baseline import fingerprint
from ramplint.linter import Violation

SCHEMA = 1


def template_scan_data(violations: Sequence[Violation], files_checked: int) -> dict[str, object]:
    """A ``scan.json`` of a template run, readable by ``--baseline``."""
    return {
        "schema": SCHEMA,
        "tool": {"name": "ramplint", "version": __version__},
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "templates",
        "files_checked": files_checked,
        "violations": [
            {**{k: v for k, v in item.to_dict().items() if k != "baseline"}, "fingerprint": fp}
            for item, fp in ((item, fingerprint(item)) for item in violations)
        ],
    }


def write_template_baseline(
    path: Path, violations: Sequence[Violation], files_checked: int
) -> None:
    """Write the baseline file (missing folders are created). Raises OSError."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = template_scan_data(violations, files_checked)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
