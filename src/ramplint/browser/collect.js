// Injected into every scanned page by ramplint (browser mode).
// Numbers every element with data-rl-node and returns what the checks and the
// report need: box, visibility, a unique CSS selector and a few computed styles.
// Read-only apart from the data-rl-node attributes. Linear in the number of
// elements: pages with tens of thousands of elements are common.
() => {
  const STYLES = [
    "color", "background-color", "background-image", "font-size", "font-weight",
    "opacity", "position", "display", "visibility", "outline-style", "outline-width",
    "outline-color", "overflow-x", "overflow-y", "z-index", "box-shadow",
    "border-top-color", "border-bottom-color", "border-top-style", "text-decoration-line",
    "cursor",
  ];
  const all = Array.from(document.querySelectorAll("*"));

  // Pass 1: how many elements share an id, and a tag among siblings.
  const idCount = new Map();
  const tagCount = new Map(); // parent -> Map(tag -> count)
  for (const el of all) {
    if (el.id) idCount.set(el.id, (idCount.get(el.id) || 0) + 1);
    const parent = el.parentElement;
    if (!parent) continue;
    let counts = tagCount.get(parent);
    if (!counts) tagCount.set(parent, (counts = new Map()));
    counts.set(el.localName, (counts.get(el.localName) || 0) + 1);
  }

  // Pass 2: selectors (parents come before children in document order).
  const selector = new Map();
  const seen = new Map(); // parent -> Map(tag -> index so far)
  const selectorOf = (el) => {
    const tag = el.localName;
    if (el.id && idCount.get(el.id) === 1) return `#${CSS.escape(el.id)}`;
    if (tag === "html" || tag === "body") return tag;
    const parent = el.parentElement;
    if (!parent) return tag;
    let index = seen.get(parent);
    if (!index) seen.set(parent, (index = new Map()));
    const position = (index.get(tag) || 0) + 1;
    index.set(tag, position);
    const step = tagCount.get(parent).get(tag) > 1 ? `${tag}:nth-of-type(${position})` : tag;
    return `${selector.get(parent) || selectorOf(parent)} > ${step}`;
  };

  const visible = (el) => {
    if (typeof el.checkVisibility === "function") {
      return el.checkVisibility({ visibilityProperty: true });
    }
    const style = getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden" && el.getClientRects().length > 0;
  };

  const sx = window.scrollX;
  const sy = window.scrollY;
  const elements = [];
  all.forEach((el, position) => {
    const id = String(position + 1);
    selector.set(el, selectorOf(el));
    const rect = el.getBoundingClientRect();
    const computed = getComputedStyle(el);
    const styles = {};
    for (const name of STYLES) styles[name] = computed.getPropertyValue(name);
    elements.push({
      id,
      tag: el.localName,
      selector: selector.get(el),
      box: [rect.left + sx, rect.top + sy, rect.width, rect.height],
      visible: visible(el),
      styles,
      // Template location from ramplint's Django source map loader.
      source: el.getAttribute("data-rl-src"),
    });
  });
  // Colours of elements with their own text, for the contrast check. The
  // background is every background colour from the element up to the first
  // opaque one; images and gradients on the way are flagged.
  const MAX_TEXTS = 3000;
  const texts = [];
  const ownText = (el) =>
    Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && n.data.trim());
  const opaque = (color) => /^rgb\(/.test(color) || /,\s*1\)$/.test(color);
  all.forEach((el, position) => {
    if (texts.length >= MAX_TEXTS || !elements[position].visible || !ownText(el)) return;
    if (["script", "style", "noscript", "template", "title", "option"].includes(el.localName)) return;
    const style = getComputedStyle(el);
    const backgrounds = [];
    let overImage = false;
    let opacity = 1;
    for (let node = el; node; node = node.parentElement) {
      const s = node === el ? style : getComputedStyle(node);
      opacity *= parseFloat(s.opacity) || 0;
      if (s.backgroundImage && s.backgroundImage !== "none") overImage = true;
      const color = s.backgroundColor;
      if (color && color !== "transparent" && color !== "rgba(0, 0, 0, 0)") {
        backgrounds.push(color);
        if (opaque(color)) break;
      }
      if (overImage) break;
    }
    texts.push({
      element: String(position + 1),
      color: style.color,
      backgrounds,
      over_image: overImage,
      font_size: parseFloat(style.fontSize) || 16,
      font_weight: parseInt(style.fontWeight, 10) || 400,
      opacity,
    });
  });

  // Only now: changing attributes in the loops above would make the browser
  // recompute styles and layout for every element.
  all.forEach((el, position) => {
    el.setAttribute("data-rl-node", String(position + 1));
    // Rules must never see the source map.
    el.removeAttribute("data-rl-src");
  });
  const root = document.documentElement;
  // A JSON string crosses the browser boundary much faster than an object tree.
  return JSON.stringify({
    elements,
    texts,
    page: [root.scrollWidth, root.scrollHeight],
    title: document.title,
  });
}
