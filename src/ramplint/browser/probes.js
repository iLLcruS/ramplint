// Helpers for the probes (ramplint/browser/probes.py), installed once per page
// as window.__ramplint. They only read the page, apart from the data-rl-*
// marker attributes and the guards that stop the page from leaving or sending
// data while menus and dialogs are explored.
() => {
  if (window.__ramplint) return;

  const FOCUS_STYLES = [
    "outline-style", "outline-width", "outline-color", "outline-offset", "box-shadow",
    "border-top-color", "border-right-color", "border-bottom-color", "border-left-color",
    "border-top-width", "background-color", "color", "text-decoration-line",
  ];

  const cssPath = (el) => {
    const steps = [];
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (node.id && document.querySelectorAll(`#${CSS.escape(node.id)}`).length === 1) {
        steps.unshift(`#${CSS.escape(node.id)}`);
        break;
      }
      const tag = node.localName;
      if (tag === "html" || tag === "body") {
        steps.unshift(tag);
        break;
      }
      const same = Array.from(node.parentElement ? node.parentElement.children : []).filter(
        (child) => child.localName === tag,
      );
      steps.unshift(same.length > 1 ? `${tag}:nth-of-type(${same.indexOf(node) + 1})` : tag);
    }
    return steps.join(" > ");
  };

  const visible = (el) =>
    typeof el.checkVisibility === "function"
      ? el.checkVisibility({ visibilityProperty: true })
      : el.getClientRects().length > 0;

  const label = (el) =>
    (el.getAttribute("aria-label") || el.textContent || el.getAttribute("title") || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 40);

  const signature = (el) => {
    const style = getComputedStyle(el);
    return FOCUS_STYLES.map((name) => style.getPropertyValue(name)).join("|");
  };

  // The element (or a part of it) that is on top at a point, if it is not
  // the focused element, one of its descendants or one of its ancestors.
  const coverAt = (el, x, y) => {
    const hit = document.elementFromPoint(x, y);
    if (!hit || hit === el || el.contains(hit) || hit.contains(el)) return null;
    for (let node = hit; node && node !== document.body; node = node.parentElement) {
      const position = getComputedStyle(node).position;
      if (position === "fixed" || position === "sticky") return node;
    }
    return null;
  };

  const TRIGGERS = [
    '[aria-expanded="false"]',
    '[aria-haspopup]:not([aria-haspopup="false"])',
    "[aria-controls]",
    "details > summary",
    '[role="tab"]:not([aria-selected="true"])',
    "[data-bs-toggle]",
    "[data-toggle]",
    "[popovertarget]",
    "[commandfor]",
  ].join(",");

  window.__ramplint = {
    cssPath,

    // What has focus now and how it looks, after a Tab press.
    focused() {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      const rect = el.getBoundingClientRect();
      const inset = 2;
      const points = [
        [rect.left + rect.width / 2, rect.top + rect.height / 2],
        [rect.left + inset, rect.top + inset],
        [rect.right - inset, rect.top + inset],
        [rect.left + inset, rect.bottom - inset],
        [rect.right - inset, rect.bottom - inset],
      ].filter(([x, y]) => x >= 0 && y >= 0 && x < innerWidth && y < innerHeight);
      const covers = points.map(([x, y]) => coverAt(el, x, y));
      const fullyCovered = points.length > 0 && covers.every(Boolean);
      return {
        id: el.getAttribute("data-rl-node"),
        selector: cssPath(el),
        signature: signature(el),
        rect: [rect.left, rect.top, rect.width, rect.height],
        obscuredBy: fullyCovered ? cssPath(covers[0]) : null,
      };
    },

    // Remove focus without moving the sequential focus navigation start point.
    blurActive() {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      el.blur();
      return signature(el);
    },

    focusableCount() {
      const selector =
        'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
        "select:not([disabled]), textarea:not([disabled]), [tabindex], summary, " +
        '[contenteditable="true"]';
      return Array.from(document.querySelectorAll(selector)).filter(
        (el) => visible(el) && el.tabIndex >= 0,
      ).length;
    },

    triggers(max) {
      const seen = new Set();
      const found = [];
      for (const el of document.querySelectorAll(TRIGGERS)) {
        if (found.length >= max) break;
        if (!visible(el) || seen.has(el)) continue;
        const target = el.closest("a[href]");
        // A link that also toggles something would navigate: skip it.
        if (target && !target.getAttribute("href").startsWith("#") && !el.hasAttribute("aria-controls")) {
          continue;
        }
        seen.add(el);
        const expanded = el.getAttribute("aria-expanded");
        found.push({
          selector: cssPath(el),
          label: label(el),
          tag: el.localName,
          expanded: expanded === null ? null : expanded === "true",
        });
      }
      return found;
    },

    // Remember which elements exist and which are visible before a click.
    markBefore() {
      for (const el of document.querySelectorAll("*")) {
        el.setAttribute("data-rl-before", visible(el) ? "1" : "0");
      }
    },

    // Elements that are new, or visible now but not before.
    changed() {
      const ids = [];
      for (const el of document.querySelectorAll("[data-rl-node]")) {
        const before = el.getAttribute("data-rl-before");
        if (visible(el) && before !== "1") ids.push(el.getAttribute("data-rl-node"));
      }
      return ids;
    },

    clearMarks() {
      for (const el of document.querySelectorAll("[data-rl-before]")) {
        el.removeAttribute("data-rl-before");
      }
    },

    // Resolves when the DOM had no changes for `quiet` ms (at most `max` ms).
    settle(quiet, max) {
      return new Promise((resolve) => {
        let timer = setTimeout(done, quiet);
        const limit = setTimeout(done, max);
        const observer = new MutationObserver(() => {
          clearTimeout(timer);
          timer = setTimeout(done, quiet);
        });
        observer.observe(document.documentElement, {
          subtree: true, childList: true, attributes: true, characterData: true,
        });
        function done() {
          observer.disconnect();
          clearTimeout(timer);
          clearTimeout(limit);
          resolve();
        }
      });
    },

    expandedOf(selector) {
      const el = document.querySelector(selector);
      if (!el) return null;
      const value = el.getAttribute("aria-expanded");
      return value === null ? null : value === "true";
    },

    // The open modal dialog, if any, and whether focus is inside it.
    modalDialog() {
      const candidates = Array.from(
        document.querySelectorAll('dialog[open], [role="dialog"], [role="alertdialog"]'),
      ).filter((el) => {
        if (!visible(el)) return false;
        if (el.localName === "dialog") return el.matches(":modal");
        return el.getAttribute("aria-modal") === "true";
      });
      const dialog = candidates[candidates.length - 1];
      if (!dialog) return null;
      return { selector: cssPath(dialog), focusInside: dialog.contains(document.activeElement) };
    },

    // Focus may also go to the browser's own UI (activeElement is <body>):
    // that is not leaving the dialog for the page behind it.
    focusInside(selector) {
      const dialog = document.querySelector(selector);
      const active = document.activeElement;
      if (!active || active === document.body) return true;
      return Boolean(dialog && dialog.contains(active));
    },

    // Nothing the probes do may leave the page or send a form.
    guard() {
      window.open = () => null;
      window.onbeforeunload = null;
      HTMLFormElement.prototype.submit = function () {};
      HTMLFormElement.prototype.requestSubmit = function () {};
      document.addEventListener("submit", (event) => event.preventDefault(), true);
    },

    // Elements that stick out of a narrow viewport, outermost first.
    reflow() {
      const width = document.documentElement.clientWidth;
      const offenders = [];
      for (const el of document.body ? document.body.querySelectorAll("*") : []) {
        if (offenders.length >= 5) break;
        const rect = el.getBoundingClientRect();
        if (rect.right <= width + 1 || rect.width === 0 || !visible(el)) continue;
        const parent = el.parentElement;
        if (parent && parent !== document.body && parent.getBoundingClientRect().right > width + 1) {
          continue; // the parent is reported already
        }
        // Content that needs two dimensions may scroll (WCAG 1.4.10 exception).
        if (el.closest("table, pre, code, canvas, svg, video, iframe, [role=grid]")) continue;
        let scroller = false;
        for (let node = parent; node && node !== document.body; node = node.parentElement) {
          const overflow = getComputedStyle(node).overflowX;
          if (overflow === "auto" || overflow === "scroll" || overflow === "hidden") {
            scroller = true;
            break;
          }
        }
        if (!scroller) offenders.push([cssPath(el), Math.round(rect.right)]);
      }
      return {
        width,
        scrollWidth: document.documentElement.scrollWidth,
        offenders,
      };
    },
  };
}
