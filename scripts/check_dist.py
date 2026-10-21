"""Check built distributions before they are published.

Usage: python scripts/check_dist.py dist/

Fails when the wheel or the sdist misses files that ramplint needs at
runtime (rule documentation, report assets) or when versions disagree.
"""

from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WHEEL_REQUIRED = [
    "ramplint/__init__.py",
    "ramplint/py.typed",
    "ramplint/report.css",
    "ramplint/report.js",
    "ramplint/rule_docs/README.md",
]
SDIST_REQUIRED = [
    "README.md",
    "LICENSE",
    "LICENSES/PolyForm-Small-Business-1.0.0.md",
    "LICENSES/PolyForm-Noncommercial-1.0.0.md",
    "COMMERCIAL.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "docs/rules/README.md",
    "examples/templates/base.html",
    "tests/test_rule_docs.py",
]


def source_version() -> str:
    text = (ROOT / "src" / "ramplint" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__ = "([^"]+)"', text)
    if not match:
        raise SystemExit("cannot find __version__")
    return match.group(1)


def rule_codes() -> list[str]:
    return sorted(p.stem for p in (ROOT / "docs" / "rules").glob("RL*.md"))


def main(dist: Path) -> int:
    version = source_version()
    errors: list[str] = []

    wheels = list(dist.glob("ramplint-*.whl"))
    sdists = list(dist.glob("ramplint-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(f"expected one wheel and one sdist in {dist}, found {wheels + sdists}")
    wheel, sdist = wheels[0], sdists[0]

    for artifact in (wheel, sdist):
        if f"ramplint-{version}" not in artifact.name:
            errors.append(f"{artifact.name} does not match version {version}")

    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        required = WHEEL_REQUIRED + [f"ramplint/rule_docs/{code}.md" for code in rule_codes()]
        errors += [f"wheel is missing {name}" for name in required if name not in names]
        metadata = next(n for n in names if n.endswith(".dist-info/METADATA"))
        meta = zf.read(metadata).decode("utf-8")
        if f"Version: {version}\n" not in meta:
            errors.append("wheel METADATA has the wrong version")
        if "Description-Content-Type: text/markdown" not in meta:
            errors.append("wheel METADATA is missing the Markdown description type")
        leaked = [n for n in names if "__pycache__" in n or n.startswith("tests/")]
        errors += [f"wheel should not contain {name}" for name in leaked]

    with tarfile.open(sdist) as tf:
        prefix = f"ramplint-{version}/"
        names = {member.name.removeprefix(prefix) for member in tf.getmembers()}
        errors += [f"sdist is missing {name}" for name in SDIST_REQUIRED if name not in names]

    if errors:
        print("\n".join(f"error: {e}" for e in errors), file=sys.stderr)
        return 1
    print(f"{wheel.name} and {sdist.name} look good ({len(rule_codes())} rule pages).")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "dist")))
