"""``--changed [REF]``: lint only the files changed since a git commit.

In a pull request ``ramplint --changed origin/main`` checks the templates and
forms modules the branch touched (committed, staged, unstaged and untracked),
compared with the commit where the branch left ``origin/main``. Without a
ref it checks the changes not committed yet (``HEAD``).
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path


class ChangedFilesError(Exception):
    """git cannot tell which files changed."""


def _git(args: Sequence[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        raise ChangedFilesError("--changed needs git, and git is not installed") from None
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        reason = detail[-1] if detail else f"git {args[0]} failed"
        raise ChangedFilesError(f"--changed: {reason}")
    return result.stdout


def changed_files(ref: str, cwd: Path | None = None) -> set[Path]:
    """Absolute paths of the files changed since ``ref`` (deleted files excluded)."""
    cwd = cwd or Path.cwd()
    root = Path(_git(["rev-parse", "--show-toplevel"], cwd).strip())
    base = ref
    if ref != "HEAD":
        base = _git(["merge-base", ref, "HEAD"], cwd).strip() or ref
    names = _git(["diff", "--name-only", "--diff-filter=d", "-z", base, "--"], cwd).split("\0")
    untracked = _git(["ls-files", "--others", "--exclude-standard", "-z"], root).split("\0")
    return {(root / name).resolve() for name in (*names, *untracked) if name}


def only_changed(files: Iterable[Path], changed: set[Path]) -> list[Path]:
    """The ``files`` that are in ``changed``, in their order."""
    return [path for path in files if path.resolve() in changed]
