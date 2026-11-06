"""Create the GitHub milestone, labels and issues for ramplint 0.7.0 (browser scan mode).

Usage:
    python scripts/create_issues_0_7_0.py --dry-run     # show what would be created
    python scripts/create_issues_0_7_0.py               # create everything

Requires the GitHub CLI (https://cli.github.com) logged in with `gh auth login`.
Safe to run again: labels, the milestone and issues that already exist (same
title) are reused, never duplicated.
"""

# ruff: noqa: E501 - issue texts are Markdown, long lines are intended.
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap

REPO = "iLLcruS/ramplint"
MILESTONE = "0.7.0"
MILESTONE_DESCRIPTION = (
    "Browser scan mode: crawl a running site, discover its endpoints, check the rendered "
    "pages, take screenshots and map every problem back to the template that produced it."
)

LABELS = {
    "browser": ("1d76db", "Browser scan mode"),
    "discovery": ("5319e7", "Finding pages and endpoints"),
    "rules": ("0e8a16", "Accessibility rules"),
    "report": ("fbca04", "Output formats and reports"),
    "django": ("0c4b33", "Django integration"),
    "ci": ("bfd4f2", "Tests, CI and packaging"),
    "docs": ("c5def5", "Documentation"),
    "enhancement": ("a2eeef", "New feature or request"),
    "epic": ("3e4b9e", "Tracking issue for a release feature"),
}


def body(text: str) -> str:
    return textwrap.dedent(text).strip() + "\n"


EPIC_TITLE = "Browser scan mode (0.7.0)"
EPIC_BODY = body(
    """
    ramplint reads templates. A template is not the page the user gets: JavaScript adds
    markup, CSS decides colours and sizes, and some problems (contrast, focus, reflow,
    target size) only exist in a rendered page. 0.7.0 adds a browser scan mode that
    opens a running site in Chromium, finds its pages and endpoints, checks what is
    actually rendered and writes a report with screenshots - and still points every
    problem at the template line that produced it.

    ```console
    $ pip install "ramplint[browser]" && playwright install chromium
    $ ramplint http://localhost:8000                # scan a running site
    $ ramplint --runserver                          # start the Django project and scan it
    $ ramplint --runserver --format html -o a11y/   # report with screenshots
    ```

    ## How it works

    ```mermaid
    flowchart LR
      U[URLconf via ast] --> F[Frontier]
      S[sitemap.xml / robots.txt] --> F
      C[links, GET forms, hx-get] --> F
      F -->|next URL| P[Chromium page]
      P --> N[network log: XHR / fetch]
      N --> I[API inventory]
      P --> X[Snapshot: DOM, boxes, AX tree, screenshots]
      X --> R1[RL1-RL7 on rendered DOM]
      X --> R8[RL8xx rendered-page rules]
      X --> ST[States: menus, dialogs, details]
      ST --> X
      R1 & R8 --> M[Source map: page element -> template:line]
      M --> D[Dedupe across pages]
      D --> R9[RL9xx site-wide rules]
      D --> O[Report: HTML + screenshots, JSON, SARIF]
    ```

    1. **Discovery.** URL patterns come from the Django URLconf (read with `ast`, never
       imported), `sitemap.xml`, and the pages themselves: links, GET forms, HTMX
       `hx-get` attributes. XHR and `fetch` calls seen while a page loads form an API
       inventory.
    2. **Smart frontier.** Every URL is matched to its pattern (`/products/42/` ->
       `products/<int:pk>/`). ramplint scans a few URLs per pattern instead of
       thousands of product pages, scans unvisited patterns first, and reports which
       patterns it could not reach and why (needs a sample URL, needs login, 404, 500).
    3. **Snapshot.** For each page and viewport: rendered DOM, bounding box of every
       element, accessibility tree, viewport and full-page screenshots.
    4. **Checks.** The existing RL1xx-RL7xx rules run on the rendered DOM. New RL8xx
       rules check what only a browser knows (contrast, target size, reflow, focus).
       RL9xx rules compare pages with each other (titles, navigation, link names).
    5. **States.** Menus, dialogs, tabs and `<details>` are opened one by one and the
       new markup is checked too. Navigation and non-GET requests are blocked while
       this happens, so nothing is submitted or deleted.
    6. **Template source map.** With `--runserver`, Django renders templates through a
       dev-only loader that adds `data-rl-src="templates/partials/nav.html:14:5"` to
       every element. A contrast problem on 37 pages becomes one problem in
       `partials/nav.html:14`, SARIF and GitHub annotations land on the template, and a
       finding seen by both the static and the browser check is reported once.
    7. **Report.** A report folder: the usual HTML report plus a page per URL with a
       screenshot, numbered markers on the problems and a crop of each element, a site
       map of URL patterns and their coverage, and the API inventory. `scan.json` keeps
       everything for tools and for `--baseline`.

    ## Principles

    - The core package stays dependency-free. Playwright comes with the optional
      `ramplint[browser]` extra; without it the browser options explain how to install it.
    - Safe by default: same origin only, GET only, a deny list (`logout`, `delete`,
      `/admin/`), a page limit and a delay between requests.
    - Every finding knows its URL, CSS selector, viewport and screenshot; with the
      source map it also knows its template file and line.
    - The HTML report still passes ramplint itself.

    ## Tasks

    <!-- tasks -->
    """
)

ISSUES: list[dict[str, object]] = [
    {
        "key": "session",
        "title": "Browser mode: `ramplint[browser]` extra, Chromium session and CLI options",
        "labels": ["browser", "enhancement"],
        "body": body(
            """
            Part of the browser scan mode epic.

            ## What

            - New optional extra in `pyproject.toml`: `browser = ["playwright>=1.45"]`.
              The core package keeps zero dependencies.
            - New package `ramplint.browser` with a `BrowserSession` that launches Chromium
              (headless by default, `--headed` for debugging), creates one context per
              viewport and closes everything on errors and Ctrl+C.
            - `ramplint URL ...` switches to browser mode when a path starts with `http://`
              or `https://`. Files and URLs can not be mixed in one run (clear error).
            - New options:
              - `--max-pages N` (default 50), `--per-pattern N` (default 2)
              - `--viewport desktop,mobile` (`desktop` = 1280x800, `mobile` = 390x844, or `WxH`)
              - `--headed`, `--timeout SECONDS` (per page, default 30), `--delay MS`
              - `--include GLOB` / `--exclude-url GLOB` for URLs
              - `--no-crawl` to scan only the given URLs
            - `[tool.ramplint.browser]` in `pyproject.toml` with the same keys
              (`base-url`, `max-pages`, `per-pattern`, `viewports`, `include`, `exclude`,
              `deny`, `wait-for`). Unknown keys are an error, like the rest of the config.
            - When Playwright or Chromium is missing: exit code 2 and the exact commands
              (`pip install "ramplint[browser]"`, `playwright install chromium`).

            ## Done when

            - `ramplint http://localhost:8000 --no-crawl` opens the page and exits 0/1.
            - `ramplint --help` documents the new options in their own argument group.
            - Unit tests cover argument parsing, config loading and the missing-dependency
              message without needing a browser.
            """
        ),
    },
    {
        "key": "snapshot",
        "title": "Browser mode: page snapshot (rendered DOM, element boxes, accessibility tree, screenshots)",
        "labels": ["browser", "enhancement"],
        "body": body(
            """
            Part of the browser scan mode epic. Depends on the browser session.

            Everything the checks and the report need is captured once per page and
            viewport into a `PageSnapshot`, so rules never talk to the browser directly
            and can be unit-tested with saved snapshots.

            ## What

            - Wait for the page: `load`, then network idle (bounded by `--timeout`), then
              the optional `wait-for` selector from the config.
            - An injected script gives every element a stable `data-rl-node` number and
              collects per element: bounding box, visibility (`display`, `visibility`,
              `opacity`, zero size, off-screen), the computed styles the rules need
              (colours, font size and weight, outline, overflow, position) and a unique
              CSS selector.
            - `page.content()` after the script runs, parsed with the existing
              `ramplint.dom.parse`, so the rendered tree is a normal `Node` tree that knows
              each node's `data-rl-node`.
            - Accessibility tree from CDP (`Accessibility.getFullAXTree`): computed role
              and accessible name per node.
            - Screenshots: viewport and full page (JPEG, quality 70; PNG with
              `--screenshot-format png`), plus element crops on demand with a few pixels
              of padding.
            - HTTP status, final URL after redirects, `<title>`, console errors.
            - `PageSnapshot.save(dir)` / `load(dir)` for tests and for regenerating reports.

            ## Done when

            - A snapshot of `examples/django_project` pages can be saved and loaded.
            - Pages with long lazy-loaded content and pages that never reach network idle
              are both handled within the timeout.
            """
        ),
    },
    {
        "key": "rendered-rules",
        "title": "Browser mode: run RL1xx-RL7xx on the rendered DOM; findings with URL, selector and screenshot",
        "labels": ["browser", "rules"],
        "body": body(
            """
            Part of the browser scan mode epic. Depends on the page snapshot.

            ## What

            - Run every selected template rule on the rendered tree of each page. No
              template preprocessing is needed: the rendered page has no `{{ }}` and no
              `{% %}`, so rules see the real attributes and text.
            - Skip elements that are not rendered (hidden, `display: none`) for rules where
              that matters, the way assistive technology does.
            - Use the accessibility tree where it is more exact than markup (e.g. an
              accessible name set by `aria-labelledby` pointing into JS-inserted content).
            - Extend `Violation` without breaking the Python API: new fields with
              `compare=False` and default `None`: `url`, `selector`, `viewport`, `bbox`,
              `screenshot`, `template` (filled by the source map), `pages` (all URLs where the
              same finding was seen).
            - Findings with the same rule, selector and message on the same URL pattern are
              merged into one finding that lists its pages.

            ## Done when

            - A button whose name is added by JavaScript is not reported; a button that
              loses its name at runtime is.
            - `lint_source` and the template mode behave exactly as before (existing tests
              unchanged).
            """
        ),
    },
    {
        "key": "urlconf",
        "title": "Discovery: read URL patterns from the Django URLconf with ast",
        "labels": ["discovery", "django"],
        "body": body(
            """
            Part of the browser scan mode epic.

            ramplint already reads Django settings without importing them. Do the same for
            URLs, so the crawler knows every page the project has - also the ones no link
            points to.

            ## What

            - `ROOT_URLCONF` from the settings that `Workspace` already finds, then the
              module file, then `urlpatterns`:
              - `path()`, `re_path()`, `url()`; list literals, `+=`, `.extend()`, `.append()`
              - `include("app.urls")`, `include((patterns, "app"))`, `include(module)`,
                `namespace=` and `app_name`
              - `i18n_patterns(...)` (prefix with the default language code)
              - `static(...)` and `debug_toolbar` URLs are ignored
              - DRF `DefaultRouter` / `SimpleRouter`: `router.register(prefix, ...)` gives
                API patterns (list and detail)
            - Each pattern: route string, converters (`<int:pk>`, `<slug:slug>`, regex
              groups), name, view (dotted path as written), source file and line.
            - Patterns without parameters become start URLs. Patterns with parameters wait
              for real URLs from the crawl or for samples from the config:

              ```toml
              [tool.ramplint.browser.samples]
              "catalog:product-detail" = ["/products/1/"]
              ```
            - What can not be resolved statically (computed lists, unknown helpers) is
              listed in `--verbose` output instead of failing.
            - `ramplint --list-urls` prints the patterns (text or json), like `--list-templates`.

            ## Done when

            - `ramplint --list-urls` works on `examples/django_project` and on a project with
              nested includes, namespaces, i18n patterns and a DRF router (test fixtures).
            """
        ),
    },
    {
        "key": "crawl",
        "title": "Discovery: links, sitemap.xml, GET forms, HTMX attributes and an API inventory from network traffic",
        "labels": ["discovery", "browser"],
        "body": body(
            """
            Part of the browser scan mode epic. Depends on the page snapshot.

            ## What

            - From each rendered page: `a[href]`, `area[href]`, `link[rel=next|prev]`,
              `iframe[src]` (same origin), `form[method=get][action]` (submitted without
              values), `meta[http-equiv=refresh]`.
            - HTMX: `hx-get` URLs are fragments - lint them as partials (no document rules
              like `html-lang`). `hx-post`/`hx-put`/`hx-delete` are listed, never called.
            - `robots.txt` (for `Sitemap:` lines) and `sitemap.xml` / sitemap indexes.
            - Network log per page: every XHR and `fetch` request with method, URL, status,
              content type, size and the page that made it. Responses with
              `text/html` are queued as fragments; JSON and other types go to the API
              inventory in the report (grouped by URL pattern).
            - Redirects and their targets, 4xx and 5xx pages are recorded for the site map.

            ## Done when

            - Crawling `examples/django_project` from `/` finds every linked page.
            - A page that loads a list with `fetch('/api/items/')` shows that endpoint in the
              API inventory with its method and status.
            """
        ),
    },
    {
        "key": "frontier",
        "title": "Discovery: smart crawl frontier (URL patterns, budget, coverage, safety)",
        "labels": ["discovery", "browser"],
        "body": body(
            """
            Part of the browser scan mode epic. Depends on URLconf discovery and crawling.

            A site with 10 000 product pages has one product template. The frontier makes
            the crawl spend its page budget on different templates, not on more of the same.

            ## What

            - URL normalization: drop fragments, sort query parameters, drop tracking
              parameters (`utm_*`, `fbclid`, `gclid`), resolve `..`, keep one trailing-slash
              form.
            - Match each URL to a URLconf pattern. Without a URLconf (any non-Django site),
              infer patterns from path segments: numbers, UUIDs, dates, and segments that
              vary across sibling URLs become `{param}`.
            - Budget: at most `--per-pattern` URLs per pattern and `--max-pages` in total.
              Priority: start URLs, then patterns not yet visited, then by link depth.
              Query-string variations of a pattern (`?page=2`, `?sort=`) count as the same
              pattern.
            - Safety:
              - same origin as the start URL only
              - GET only; never submits POST forms
              - deny list (config `deny`, defaults: `logout`, `signout`, `delete`, `remove`,
                `/admin/`), checked against the URL and the URL pattern name
              - `--delay` between requests, one page at a time by default (`--concurrency N`)
            - Coverage for the report: each pattern is `scanned`, `needs sample` (has
              parameters, no URL found), `needs login` (redirected to the login URL),
              `denied`, `error` (status) or `skipped` (budget).

            ## Done when

            - A crawl of a fixture with 500 product links scans 2 product pages and reports
              the pattern as `scanned (2 of 500)`.
            - A `/logout/` link is never opened.
            """
        ),
    },
    {
        "key": "states",
        "title": "Browser mode: open menus, dialogs, tabs and details, and check the new markup",
        "labels": ["browser", "enhancement"],
        "body": body(
            """
            Part of the browser scan mode epic. Depends on the page snapshot.

            Many problems sit in markup that is only visible after a click: a dropdown menu,
            a modal dialog, an accordion panel, a tab panel.

            ## What

            - Find triggers on the page: `[aria-expanded="false"]`, `[aria-haspopup]`,
              `[aria-controls]`, `summary`, `[role=tab]`, `[data-bs-toggle]`,
              `[popovertarget]`, buttons that control a `<dialog>`.
            - For each trigger (limit per page, `--max-states`, default 10): reset the page,
              click the trigger, wait for the DOM to settle (MutationObserver), take a
              snapshot, check only the elements that changed or became visible.
            - While states are explored, the page can not leave or change anything:
              navigations are aborted, every non-GET request is aborted (Playwright
              `route`), `window.open` and `beforeunload` are stubbed.
            - Findings in a state carry the state description
              (`after clicking "Menu" (button#nav-toggle)`) and its screenshot.
            - Also checks the state itself: an opened dialog must get focus (RL806 in the
              rendered-page rules issue) and the trigger's `aria-expanded` must become `true`.

            ## Done when

            - A Bootstrap navbar dropdown and a `<dialog>` in a fixture page are opened and
              checked; a delete button inside the dialog is never sent.
            """
        ),
    },
    {
        "key": "sourcemap",
        "title": "Django: template source maps and `--runserver` (findings point at template:line)",
        "labels": ["django", "browser"],
        "body": body(
            """
            Part of the browser scan mode epic. This is what makes the browser mode useful
            for a Django developer: a problem is not "somewhere on /products/42/" but
            "`catalog/templates/catalog/product_list.html:14:9`".

            ## What

            - `ramplint.django.SourceMapLoader`: a template loader wrapper that, only when
              `DEBUG` is on, adds `data-rl-src="<path>:<line>:<col>"` to every start tag in
              the template source before Django compiles it. Positions come from
              `ramplint.template.prepare`, so they are the same positions the static mode
              reports. Tags inside `<script>`, `<style>`, attribute values and
              `{% verbatim %}` are left alone. Included templates carry their own path.
            - `--runserver`: start the project found in the current folder with
              `python manage.py runserver 127.0.0.1:<free port> --noreload` and a generated
              settings module that does `from <project settings> import *` and wraps the
              template loaders with `SourceMapLoader` - no change to the user's settings.
              ramplint waits for the server, scans it, and stops it. Server output goes to
              `--verbose`.
            - Manual setup for other servers documented: add the loader to
              `TEMPLATES[...]["OPTIONS"]["loaders"]` in dev settings.
            - In findings: `template = (path, line, col)`; reporters that show a file
              (text, github, sarif) use the template location when it is known and the URL
              otherwise.
            - Dedupe: the same rule on the same template location is one finding, with the
              list of pages where it was seen. A static finding and a browser finding on the
              same template location are merged and marked as confirmed in the browser.
            - The `data-rl-src` attributes are removed from the DOM the rules see, so they
              never affect results.

            ## Done when

            - `ramplint --runserver` on `examples/django_project` reports browser findings
              with template paths and lines, and GitHub annotations land on the templates.
            - Jinja2 templates fall back to URL + selector (Jinja2 source maps later).
            """
        ),
    },
    {
        "key": "rl8",
        "title": "Rules: rendered-page checks RL801-RL806 (contrast, target size, reflow, focus)",
        "labels": ["rules", "browser"],
        "body": body(
            """
            Part of the browser scan mode epic. Depends on the page snapshot.

            New rule group RL8xx for checks that need a rendered page. Each rule gets a page
            in `docs/rules/` and works with `--select`, `--ignore`, `--explain` and
            `--list-rules` (marked `[browser]`). In template mode they are skipped.

            | Code | Name | WCAG | Check |
            |---|---|---|---|
            | RL801 | `color-contrast` | 1.4.3 | Text contrast of at least 4.5:1, 3:1 for large text. Colours composited through transparent ancestors; text over images or gradients is reported as "needs manual check", not as a failure. |
            | RL802 | `target-size` | 2.5.8 | Clickable targets of at least 24x24 CSS px, or with enough spacing; inline links in text are exempt. |
            | RL803 | `reflow` | 1.4.10 | At a 320 CSS px wide viewport the page scrolls horizontally; reports the widest elements. |
            | RL804 | `focus-visible` | 2.4.7 | Tab through the page; an element that looks the same focused and unfocused (styles and a pixel diff of its box). |
            | RL805 | `focus-obscured` | 2.4.11 | The focused element is fully covered by a sticky header, footer or cookie banner (`elementFromPoint`). |
            | RL806 | `dialog-focus` | 2.4.3 | An opened modal dialog does not move focus into itself, or Tab leaves it while it is open. |

            Tab order is recorded once per page (up to 200 stops) and shared by RL804-RL806;
            a page where Tab never leaves a small group of elements is reported as a keyboard
            trap (2.1.2) by RL806.

            ## Done when

            - Each rule has passing and failing fixture pages and a docs page.
            - Contrast results match a reference implementation on a fixture of 50 colour
              pairs (including alpha).
            """
        ),
    },
    {
        "key": "rl9",
        "title": "Rules: site-wide checks RL901-RL904 (titles, consistent navigation and names, skip link)",
        "labels": ["rules", "browser"],
        "body": body(
            """
            Part of the browser scan mode epic. Depends on crawling.

            A crawl sees many pages at once, so it can check what no single-page tool can:
            whether the pages agree with each other.

            | Code | Name | WCAG | Check |
            |---|---|---|---|
            | RL901 | `page-title-unique` | 2.4.2 | Different URL patterns with the same `<title>`. |
            | RL902 | `consistent-navigation` | 3.2.3 | The links of the same `<nav>` (by label or position) come in a different order on different pages. |
            | RL903 | `consistent-identification` | 3.2.4 | Links to the same URL, or buttons with the same icon, with different accessible names across pages. |
            | RL904 | `bypass-blocks` | 2.4.1 | Pages with repeated navigation before `<main>` and neither a skip link nor a `<main>` landmark that can be reached. |

            Findings list the pages involved and, with the source map, the template.

            ## Done when

            - Fixture sites with and without each problem; results do not depend on crawl order.
            """
        ),
    },
    {
        "key": "auth",
        "title": "Browser mode: scan pages behind login (`--save-auth`, `--auth`)",
        "labels": ["browser", "enhancement"],
        "body": body(
            """
            Part of the browser scan mode epic.

            Most of a Django app is behind login. ramplint must never ask for or store
            passwords.

            ## What

            - `ramplint --save-auth auth.json http://localhost:8000/accounts/login/` opens a
              headed browser; the user logs in by hand and closes the window; cookies and
              local storage are saved as a Playwright storage state.
            - `--auth auth.json` (or `auth = "auth.json"` in `[tool.ramplint.browser]`)
              loads it for the scan. Several files (`--auth admin.json --auth customer.json`)
              scan the site once per role; findings say which role saw them.
            - Detect an expired session: redirects to the login URL (`LOGIN_URL` from the
              settings when known) mark pages as `needs login` and print a hint to run
              `--save-auth` again.
            - Warn when the auth file is inside the repository and not ignored by git.

            ## Done when

            - A fixture with a login-protected page is scanned with a saved state and shows
              `needs login` without it.
            """
        ),
    },
    {
        "key": "report",
        "title": "Report: scan folder with screenshots, problem markers, site map and API inventory",
        "labels": ["report", "browser"],
        "body": body(
            """
            Part of the browser scan mode epic. Depends on the snapshot and the findings.

            ## What

            - `--format html -o a11y/` in browser mode writes a folder:
              - `index.html` - the existing report (summary, rules table, filters) with
                browser findings, grouped by template when the source map is on and by URL
                pattern otherwise
              - `pages/<slug>.html` - one page per scanned URL and viewport: the screenshot
                with numbered markers on the problem elements, and an ordered list of the
                problems with an element crop each. The markers are decorative
                (`aria-hidden`); the list is the accessible version and links to the
                markers.
              - `site-map.html` - URL patterns as a tree with coverage status
                (scanned / needs sample / needs login / denied / error / skipped), status
                codes and redirect targets
              - `api.html` - the API inventory: method, URL pattern, status, content type,
                pages that call it
              - `screenshots/` - images referenced by the pages
              - `scan.json` - everything above, machine-readable and versioned
                (`"schema": 1`)
            - `--embed-screenshots` writes a single HTML file with images as data URIs
              (warns above 20 MB).
            - `json`, `text`, `github` and `sarif` formats include URL, selector, viewport,
              state and template location. SARIF: template location as the physical
              location when known; the URL as a `logicalLocation` and in `properties`.
            - Every generated page passes ramplint (checked in CI), works offline, and
              follows the light/dark theme like the current report.

            ## Done when

            - A report of `examples/django_project` opens from disk without a server and
              without JavaScript (filters need JS, everything else does not).
            """
        ),
    },
    {
        "key": "baseline",
        "title": "Browser mode: `--baseline scan.json` to report only new problems",
        "labels": ["browser", "report"],
        "body": body(
            """
            Part of the browser scan mode epic. Depends on `scan.json`.

            Turning on a browser scan on an existing site shows hundreds of old problems.
            A baseline lets a team fail CI only on new ones and fix the old ones over time.

            ## What

            - `--baseline previous/scan.json`: each finding is `new`, `existing` or `fixed`.
              Matching uses a fingerprint that survives unrelated changes: rule +
              template location (with source map), otherwise rule + URL pattern + selector
              without `:nth-child` indices + normalized message.
            - Exit code 1 only for `new` findings when a baseline is given.
            - The HTML report shows new/fixed counts and a filter; text output shows only new
              findings plus a one-line summary of existing and fixed.
            - `--write-baseline FILE` as a shortcut for writing `scan.json` only.

            ## Done when

            - Moving an element inside a template keeps its finding `existing`; fixing it
              makes it `fixed`; adding a new one fails the run.
            """
        ),
    },
    {
        "key": "ci",
        "title": "CI: browser test job, fixture site and coverage",
        "labels": ["ci"],
        "body": body(
            """
            Part of the browser scan mode epic.

            ## What

            - Unit tests for discovery, the frontier, rules and reports run on saved
              `PageSnapshot` fixtures - no browser - in the existing test matrix.
            - New `browser` job (Ubuntu, Python 3.13): `pip install -e ".[dev,browser]"`,
              `playwright install --with-deps chromium`, integration tests marked
              `@pytest.mark.browser` against `examples/django_project` (served with
              `--runserver`) and a small static fixture site (`tests/sites/`) for the
              non-Django cases (HTMX, fetch API, dialogs, 500 product links).
            - Coverage from both jobs is combined before the 95% threshold is checked.
            - `package` job: install the wheel with the `browser` extra and run a real scan
              of the demo; the report folder must pass `ramplint` itself.
            - `scripts/check_dist.py` checks the new package data (report assets, JS
              helpers injected into pages).

            ## Done when

            - CI is green on all jobs and the browser job takes under 5 minutes.
            """
        ),
    },
    {
        "key": "docs",
        "title": "Docs and release 0.7.0",
        "labels": ["docs"],
        "body": body(
            """
            Part of the browser scan mode epic.

            ## What

            - README: "Browser scan" section (install, `--runserver`, scanning any URL,
              login, report folder with a screenshot, baseline in CI), new rules in the
              rules list, update "Limitations" (contrast and focus are now checked in
              browser mode) and the roadmap.
            - `docs/rules/RL801.md`-`RL806.md`, `RL901.md`-`RL904.md`.
            - GitHub Actions example: start the Django app, scan with a baseline, upload the
              report folder as an artifact and SARIF to Code Scanning.
            - CHANGELOG, version bump, release notes with a report screenshot.
            """
        ),
    },
]


class GitHub:
    def __init__(self, repo: str, dry_run: bool) -> None:
        self.repo = repo
        self.dry_run = dry_run

    def api(self, method: str, path: str, payload: dict | None = None) -> object:
        cmd = ["gh", "api", "--method", method, f"repos/{self.repo}/{path}"]
        data = None
        if payload is not None:
            cmd += ["--input", "-"]
            data = json.dumps(payload).encode("utf-8")
        result = subprocess.run(cmd, input=data, capture_output=True)
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"gh api {method} {path} failed: {message}")
        out = result.stdout.decode("utf-8")
        return json.loads(out) if out.strip() else None

    def get_all(self, path: str) -> list[dict]:
        items: list[dict] = []
        page = 1
        sep = "&" if "?" in path else "?"
        while True:
            chunk = self.api("GET", f"{path}{sep}per_page=100&page={page}")
            if not chunk:
                return items
            items.extend(chunk)  # type: ignore[arg-type]
            page += 1

    def write(self, method: str, path: str, payload: dict, what: str) -> dict:
        if self.dry_run:
            print(f"  [dry-run] {what}")
            return {"number": 0, "id": 0, "html_url": "(dry run)"}
        return self.api(method, path, payload)  # type: ignore[return-value]


def ensure_labels(gh: GitHub) -> None:
    print("Labels")
    existing = {label["name"].lower() for label in gh.get_all("labels")}
    for name, (color, description) in LABELS.items():
        if name.lower() in existing:
            print(f"  exists: {name}")
            continue
        gh.write(
            "POST",
            "labels",
            {"name": name, "color": color, "description": description},
            f"create label {name}",
        )
        print(f"  created: {name}")


def ensure_milestone(gh: GitHub) -> int:
    print("Milestone")
    for milestone in gh.get_all("milestones?state=all"):
        if milestone["title"] == MILESTONE:
            print(
                f"  exists: {MILESTONE} (#{milestone['number']}, {milestone['state']})"
            )
            return milestone["number"]
    created = gh.write(
        "POST",
        "milestones",
        {"title": MILESTONE, "description": MILESTONE_DESCRIPTION},
        f"create milestone {MILESTONE}",
    )
    print(f"  created: {MILESTONE}")
    return created["number"]


def existing_issues(gh: GitHub) -> dict[str, dict]:
    issues = gh.get_all("issues?state=all")
    return {i["title"]: i for i in issues if "pull_request" not in i}


def ensure_issue(
    gh: GitHub,
    known: dict[str, dict],
    title: str,
    text: str,
    labels: list[str],
    milestone: int,
) -> dict:
    if title in known:
        issue = known[title]
        print(f"  exists: #{issue['number']} {title}")
        return issue
    payload: dict[str, object] = {"title": title, "body": text, "labels": labels}
    if milestone:
        payload["milestone"] = milestone
    issue = gh.write("POST", "issues", payload, f"create issue: {title}")
    if not gh.dry_run:
        print(f"  created: #{issue['number']} {title}")
    known[title] = issue
    return issue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=REPO, help=f"owner/name (default: {REPO})")
    parser.add_argument(
        "--dry-run", action="store_true", help="only show what would be done"
    )
    args = parser.parse_args()

    if shutil.which("gh") is None:
        print(
            "error: GitHub CLI not found. Install it from https://cli.github.com",
            file=sys.stderr,
        )
        return 2
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        print("error: not logged in. Run: gh auth login", file=sys.stderr)
        return 2

    gh = GitHub(args.repo, args.dry_run)
    try:
        ensure_labels(gh)
        milestone = ensure_milestone(gh)
        known = existing_issues(gh)

        print("Issues")
        epic = ensure_issue(
            gh,
            known,
            EPIC_TITLE,
            EPIC_BODY,
            ["epic", "browser", "enhancement"],
            milestone,
        )
        children = [
            ensure_issue(
                gh,
                known,
                str(spec["title"]),
                str(spec["body"]),
                list(spec["labels"]),
                milestone,
            )  # type: ignore[arg-type]
            for spec in ISSUES
        ]

        # Task list in the epic, so GitHub shows progress.
        tasks = "\n".join(f"- [ ] #{child['number']}" for child in children)
        if not gh.dry_run:
            current = gh.api("GET", f"issues/{epic['number']}")["body"] or ""  # type: ignore[index]
            if "<!-- tasks -->" in current:
                gh.api(
                    "PATCH",
                    f"issues/{epic['number']}",
                    {"body": current.replace("<!-- tasks -->", tasks)},
                )
                print(f"  epic #{epic['number']}: task list added")

            # Native sub-issues where the repository supports them; the task list above
            # is enough when it does not.
            try:
                linked = {
                    s["number"]
                    for s in gh.get_all(f"issues/{epic['number']}/sub_issues")
                }
            except RuntimeError:
                linked = set()
            for child in children:
                if child["number"] in linked:
                    continue
                try:
                    gh.api(
                        "POST",
                        f"issues/{epic['number']}/sub_issues",
                        {"sub_issue_id": child["id"]},
                    )
                except RuntimeError as exc:
                    print(
                        f"  note: sub-issue link for #{child['number']} skipped ({exc})"
                    )
                    break
            print(f"\nDone: {epic['html_url']}")
        else:
            print(f"  [dry-run] add task list with {len(children)} issues to the epic")
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
