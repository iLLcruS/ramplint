"""ramplint - accessibility linter for Django and Jinja2 templates."""

__version__ = "0.5.0"

from ramplint.linter import Violation, iter_template_files, lint_file, lint_source  # noqa: E402
from ramplint.rules import all_rules, select_rules  # noqa: E402

__all__ = [
    "__version__",
    "Violation",
    "all_rules",
    "iter_template_files",
    "lint_file",
    "lint_source",
    "select_rules",
]
