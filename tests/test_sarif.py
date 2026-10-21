from __future__ import annotations

import io
import json
from pathlib import Path

import jsonschema

from ramplint.cli import EXIT_OK, main
from ramplint.linter import Violation
from ramplint.reporters import REPORTERS
from ramplint.rules import all_rules

SCHEMA = json.loads(
    (Path(__file__).parent / "data" / "sarif-schema-2.1.0.json").read_text(encoding="utf-8")
)

VIOLATIONS = [
    Violation("templates/a.html", 3, 5, "RL101", "img-alt", "<img> is missing an alt"),
    Violation("templates/my page.html", 9, 1, "RL502", "link-name", "<a> link has no name"),
]


def render(violations, files_checked=2) -> dict:
    out = io.StringIO()
    REPORTERS["sarif"].write(violations, files_checked, out, False)
    return json.loads(out.getvalue())


def test_output_validates_against_sarif_schema():
    jsonschema.validate(render(VIOLATIONS), SCHEMA)
    jsonschema.validate(render([]), SCHEMA)


def test_driver_describes_every_rule():
    run = render(VIOLATIONS)["runs"][0]
    driver = run["tool"]["driver"]
    assert driver["name"] == "ramplint"
    assert [r["id"] for r in driver["rules"]] == [r.code for r in all_rules()]
    img_alt = next(r for r in driver["rules"] if r["id"] == "RL101")
    assert img_alt["name"] == "img-alt"
    assert img_alt["helpUri"].endswith("/docs/rules/RL101.md")
    assert "accessibility" in img_alt["properties"]["tags"]


def test_results_point_at_rules_and_locations():
    run = render(VIOLATIONS)["runs"][0]
    rules = run["tool"]["driver"]["rules"]
    first, second = run["results"]
    assert rules[first["ruleIndex"]]["id"] == first["ruleId"] == "RL101"
    location = first["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "templates/a.html"
    assert location["region"] == {"startLine": 3, "startColumn": 5}
    # URIs are percent-encoded.
    uri = second["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "templates/my%20page.html"


def test_absolute_paths_become_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    absolute = str(tmp_path / "templates" / "b.html")
    run = render([Violation(absolute, 1, 1, "RL101", "img-alt", "x")])["runs"][0]
    uri = run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "templates/b.html"


def test_cli_sarif_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "page.html").write_text('<img src="a.png">\n')
    code = main(["page.html", "--format", "sarif", "-o", "ramplint.sarif", "--exit-zero"])
    assert code == EXIT_OK
    data = json.loads((tmp_path / "ramplint.sarif").read_text())
    jsonschema.validate(data, SCHEMA)
    assert data["runs"][0]["results"][0]["ruleId"] == "RL101"
