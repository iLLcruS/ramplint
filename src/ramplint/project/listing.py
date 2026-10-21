"""``--list-templates`` and ``--verbose``: show what ramplint found."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from ramplint.project.discovery import Project
from ramplint.project.templates import TemplateIndex
from ramplint.project.workspace import Workspace


def _projects(workspace: Workspace, paths: Sequence[str] | None) -> list[Project]:
    if workspace.configured is not None:
        return [workspace.configured]
    found = dict(workspace.projects)
    starts = [Path(p) for p in paths] if paths else [workspace.cwd]
    for start in starts:
        project = workspace.project_for(start)
        if project is not None:
            found.setdefault(project.root, project)
    return sorted(found.values(), key=lambda p: p.root)


def _count(index: TemplateIndex, directory: Path) -> int:
    return sum(1 for path in index.files() if path.is_relative_to(directory))


def _overridden(index: TemplateIndex) -> list[dict[str, object]]:
    """Template names that exist in more than one folder."""
    by_name: dict[str, list[Path]] = {}
    for directory in index.dirs:
        single = TemplateIndex([directory], index.extensions)
        for path in single.files():
            name = path.relative_to(directory).as_posix()
            by_name.setdefault(name, []).append(directory)
    return [
        {"name": name, "used": dirs[0], "hidden": dirs[1:]}
        for name, dirs in sorted(by_name.items())
        if len(dirs) > 1
    ]


def _display_root(workspace: Workspace, project: Project) -> str:
    try:
        return project.root.relative_to(workspace.cwd).as_posix() or "."
    except ValueError:
        return project.root.as_posix()


def _project_data(workspace: Workspace, project: Project) -> dict[str, object]:
    dirs = [d.path for d in project.template_dirs]
    index = TemplateIndex(dirs, workspace.extensions)
    return {
        "root": _display_root(workspace, project),
        "settings_module": project.settings_module,
        "settings_source": project.settings_source,
        "from_settings": project.from_settings,
        "template_dirs": [
            {
                "path": project.relative(d.path),
                "origin": d.origin,
                "backend": d.backend,
                "templates": _count(TemplateIndex([d.path], workspace.extensions), d.path),
            }
            for d in project.template_dirs
        ],
        "overridden": [
            {
                "name": item["name"],
                "used": project.relative(item["used"]),  # type: ignore[arg-type]
                "hidden": [project.relative(p) for p in item["hidden"]],  # type: ignore[attr-defined]
            }
            for item in _overridden(index)
        ],
        "warnings": project.warnings,
    }


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _files_summary(files: list[Path]) -> str:
    modules = sum(1 for path in files if path.suffix == ".py")
    templates = _plural(len(files) - modules, "template")
    return f"{templates} and {_plural(modules, 'forms module')}" if modules else templates


def describe_projects(
    workspace: Workspace,
    paths: Sequence[str] | None,
    files: list[Path],
    output_format: str,
    out: TextIO,
) -> None:
    projects = [_project_data(workspace, p) for p in _projects(workspace, paths)]
    if output_format == "json":
        json.dump({"projects": projects, "files": len(files)}, out, indent=2)
        out.write("\n")
        return
    if not projects:
        out.write(
            "No Django project found: ramplint lints every template under the given paths\n"
            f"({_plural(len(files), 'file')}).\n"
        )
        return
    for number, project in enumerate(projects):
        if number:
            out.write("\n")
        out.write(f"Project   {project['root']}\n")
        if project["settings_module"]:
            out.write(
                f"Settings  {project['settings_module']} (from {project['settings_source']})\n"
            )
        elif project["settings_source"] == "pyproject.toml":
            out.write("Settings  template-dirs in pyproject.toml\n")
        else:
            out.write("Settings  not found\n")
        dirs = project["template_dirs"]
        if not dirs:
            out.write("No template folders found.\n")
        else:
            out.write("Template folders:\n")
            width = max(len(d["path"]) for d in dirs)  # type: ignore[index, union-attr]
            origin_width = max(len(d["origin"]) for d in dirs)  # type: ignore[index, union-attr]
            for d in dirs:  # type: ignore[union-attr]
                backend = " (jinja2)" if d["backend"] == "jinja2" else ""
                out.write(
                    f"  {d['path']:<{width}}  {d['origin']:<{origin_width}}  "
                    f"{_plural(d['templates'], 'template')}{backend}\n"
                )
        if project["overridden"]:
            out.write("Overridden templates (the first folder wins):\n")
            for item in project["overridden"]:  # type: ignore[union-attr]
                hidden = ", ".join(item["hidden"])
                out.write(f"  {item['name']}: {item['used']} hides {hidden}\n")
        if project["warnings"]:
            out.write("Warnings:\n")
            for warning in project["warnings"]:  # type: ignore[union-attr]
                out.write(f"  {warning}\n")
    out.write(f"\n{_files_summary(files)} to lint.\n")


def print_verbose(workspace: Workspace, files: list[Path], err: TextIO) -> None:
    projects = _projects(workspace, None) if workspace.projects or workspace.configured else []
    for project in projects:
        settings = (
            f"{project.settings_module} (from {project.settings_source})"
            if project.settings_module
            else "no settings"
        )
        err.write(f"ramplint: project {_display_root(workspace, project)}: {settings}\n")
        for d in project.template_dirs:
            err.write(f"ramplint:   {project.relative(d.path)} [{d.origin}]\n")
        for warning in project.warnings:
            err.write(f"ramplint:   warning: {warning}\n")
    if not projects:
        err.write("ramplint: no Django project found, linting every template under the paths\n")
    err.write(f"ramplint: {_files_summary(files)} to lint\n")
