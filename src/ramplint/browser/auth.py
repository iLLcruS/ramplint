"""Scanning pages behind a login, without ever handling a password.

``--save-auth auth.json URL`` opens a browser window at the login page; you log
in by hand and close the window, and the cookies and local storage are saved as
a Playwright storage state. ``--auth auth.json`` loads it for a scan; several
files scan the site once per role.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ramplint.browser.options import BrowserOptions


@dataclass(frozen=True)
class Role:
    """A saved login: its name in findings (the file name) and its file."""

    name: str
    path: Path

    @classmethod
    def from_path(cls, value: str | Path) -> Role:
        path = Path(value)
        return cls(path.stem, path)


def roles(paths: list[str]) -> list[Role]:
    """Roles of the given auth files; raises ValueError for files that do not exist."""
    found = [Role.from_path(p) for p in paths]
    for role in found:
        if not role.path.is_file():
            raise ValueError(f"auth file {role.path} does not exist (create it with --save-auth)")
    names = [role.name for role in found]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"two auth files are both called {duplicates[0]!r}; rename one")
    return found


def unprotected_secret(path: Path) -> bool:
    """``path`` is inside a git repository and git does not ignore it.

    Saved logins are session cookies: anyone with the file is logged in.
    """
    folder = path.resolve().parent
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return False
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(path.resolve())], cwd=folder, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return False  # no git: nothing to warn about
    return ignored.returncode == 1


#: Called with the opened login page; the default waits for the person to close it.
OnLoginPage = Callable[[Any], None]


def _wait_for_close(page: Any) -> None:
    page.wait_for_event("close", timeout=0)


def save_auth(
    url: str,
    path: Path,
    options: BrowserOptions,
    on_page: OnLoginPage = _wait_for_close,
) -> Path:
    """Open ``url`` in a browser window and save the login when it is closed."""
    from ramplint.browser.session import BrowserSession

    with BrowserSession(options) as session:
        context = session.new_context(options.viewports[0])
        try:
            page = context.new_page()
            page.goto(url, wait_until="load", timeout=1000 * options.timeout)
            on_page(page)
            path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(path))
        finally:
            context.close()
    return path
