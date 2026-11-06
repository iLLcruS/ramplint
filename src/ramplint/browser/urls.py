"""URL patterns: ``/products/42/`` and ``/products/7/`` are the same kind of page.

Pages that differ only in an id are rendered by the same view and template, so
a problem on one is the same problem on the others. Path segments that look
like ids become placeholders and query values are dropped; scheme, host, the
other segments and the query keys stay.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit

_PLACEHOLDERS = (
    (re.compile(r"^\d+$"), "<int>"),
    (re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I), "<uuid>"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "<date>"),
    # Hashes and tokens: long, hex, and with at least one digit.
    (re.compile(r"^(?=[0-9a-f]*\d)[0-9a-f]{16,}$", re.I), "<hash>"),
)


def _segment(segment: str) -> str:
    for pattern, placeholder in _PLACEHOLDERS:
        if pattern.match(segment):
            return placeholder
    return segment


def url_pattern(url: str) -> str:
    """``https://shop.test/products/42/?page=2`` -> ``https://shop.test/products/<int>/?page=``."""
    parts = urlsplit(url)
    path = "/".join(_segment(segment) for segment in (parts.path or "/").split("/"))
    keys = sorted({key for key, _ in parse_qsl(parts.query, keep_blank_values=True)})
    query = "&".join(f"{key}=" for key in keys)
    return f"{parts.scheme}://{parts.netloc}{path}" + (f"?{query}" if query else "")
