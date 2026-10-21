# Contributing to ramplint

Thanks for helping make Django sites more accessible!

## Development setup

```bash
git clone https://github.com/iLLcruS/ramplint.git
cd ramplint
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Before opening a pull request:

```bash
ruff check .
ruff format .
pytest --cov
```

## Reporting false positives

False positives are bugs. Please open an issue with the smallest template
snippet that reproduces the problem and the output of `ramplint --version`.

## Adding a rule

1. Pick a free code in the right group:

   | Group   | Area                        |
   |---------|-----------------------------|
   | `RL1xx` | Images and non-text content |
   | `RL2xx` | Tables                      |
   | `RL3xx` | Headings and structure      |
   | `RL4xx` | Forms                       |
   | `RL5xx` | Interactive controls        |
   | `RL6xx` | Document-level              |

2. Add a function decorated with `@rule(...)` in `src/ramplint/rules/`. It
   receives the parsed tree and yields `(node, message)` pairs. Import new
   modules in `src/ramplint/rules/__init__.py`.
3. Be conservative: when template placeholders make the answer unknowable
   (`{% include %}`, `{{ widget.attrs }}`, ...), stay quiet. A linter people
   trust beats a linter people disable.
4. Add tests for both failing and passing snippets in `tests/test_rules.py`.
5. Add `docs/rules/RLxxx.md` (copy an existing page) and document the rule in
   the README rules table and in `CHANGELOG.md`. Tests check that every rule
   has a page and that its examples behave as described.
