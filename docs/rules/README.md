# Rules

| Code | Name | What it checks |
|------|------|----------------|
| [RL101](RL101.md) | `img-alt` | Images must have an alt attribute. |
| [RL102](RL102.md) | `iframe-title` | Frames must have a title describing their content. |
| [RL103](RL103.md) | `video-caption` | Videos must have captions. |
| [RL104](RL104.md) | `svg-img-alt` | &lt;svg role="img"> must have an accessible name. |
| [RL105](RL105.md) | `object-alt` | &lt;object> and &lt;embed> must have a text alternative. |
| [RL106](RL106.md) | `media-autoplay` | Media must not play sound automatically. |
| [RL201](RL201.md) | `table-header` | Data tables must use &lt;th> header cells. |
| [RL202](RL202.md) | `th-scope` | scope must be row, col, rowgroup or colgroup, and only used on &lt;th>. |
| [RL203](RL203.md) | `empty-table-header` | Table header cells must have text. |
| [RL301](RL301.md) | `heading-order` | Heading levels must not skip (e.g. &lt;h2> followed by &lt;h4>). |
| [RL302](RL302.md) | `empty-heading` | Headings must have text content. |
| [RL303](RL303.md) | `duplicate-id` | id attributes must be unique within a template. |
| [RL304](RL304.md) | `list-structure` | Lists may only contain &lt;li>, and &lt;li> must be inside a list. |
| [RL305](RL305.md) | `definition-list` | &lt;dl> may only contain &lt;dt>, &lt;dd> and &lt;div> groups of them. |
| [RL306](RL306.md) | `landmark-one-main` | A page must have exactly one main landmark. |
| [RL401](RL401.md) | `form-label` | Form controls must have an associated &lt;label>. |
| [RL402](RL402.md) | `autocomplete-valid` | autocomplete must use valid autofill tokens. |
| [RL403](RL403.md) | `label-for-target` | &lt;label for> must point to an element id in the template. |
| [RL501](RL501.md) | `button-name` | Buttons must have an accessible name. |
| [RL502](RL502.md) | `link-name` | Links must have an accessible name. |
| [RL503](RL503.md) | `no-positive-tabindex` | tabindex must not be greater than 0. |
| [RL504](RL504.md) | `anchor-is-valid` | Links must point somewhere; use &lt;button> for actions. |
| [RL505](RL505.md) | `nested-interactive` | Interactive elements must not contain other interactive elements. |
| [RL506](RL506.md) | `duplicate-accesskey` | accesskey values must be unique within a template. |
| [RL601](RL601.md) | `html-lang` | The &lt;html> element must declare the page language. |
| [RL602](RL602.md) | `viewport-zoom` | The viewport meta tag must not disable zooming. |
| [RL603](RL603.md) | `document-title` | Pages must have a non-empty &lt;title>. |
| [RL604](RL604.md) | `valid-lang` | lang values must be valid language tags. |
| [RL605](RL605.md) | `meta-refresh` | Pages must not refresh or redirect after a delay. |
| [RL606](RL606.md) | `obsolete-elements` | &lt;marquee> and &lt;blink> must not be used. |
| [RL701](RL701.md) | `aria-role` | role values must be valid, non-abstract WAI-ARIA roles. |
| [RL702](RL702.md) | `aria-valid-attr` | aria-* attributes must exist in WAI-ARIA. |
| [RL703](RL703.md) | `aria-valid-attr-value` | ARIA attribute values must match the attribute's type. |
| [RL704](RL704.md) | `aria-required-attr` | Elements with a role must have the ARIA attributes that role requires. |
| [RL705](RL705.md) | `aria-hidden-focus` | Content with aria-hidden="true" must not be focusable. |
