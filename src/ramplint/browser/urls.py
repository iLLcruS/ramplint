"""URLs of a crawl: normalization, origins and URL patterns.

``/products/42/`` and ``/products/7/`` are the same kind of page: rendered by
the same view and template, so a problem on one is the same problem on the
others, and a crawl does not need to visit both. :func:`url_pattern` turns path
segments that look like ids into placeholders and drops query values.
"""

from __future__ import annotations

import posixpath
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

_PLACEHOLDERS = (
    (re.compile(r"^\d+$"), "<int>"),
    (re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I), "<uuid>"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "<date>"),
    # Hashes and tokens: long, hex, and with at least one digit.
    (re.compile(r"^(?=[0-9a-f]*\d)[0-9a-f]{16,}$", re.I), "<hash>"),
)

#: Query parameters that only track visitors and never change the page.
TRACKING_PARAMETERS = frozenset({"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "_ga"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def placeholder(segment: str) -> str | None:
    """``<int>``, ``<uuid>``, ``<date>`` or ``<hash>`` for id-like path segments."""
    for pattern, name in _PLACEHOLDERS:
        if pattern.match(segment):
            return name
    return None


def url_pattern(url: str) -> str:
    """``https://shop.test/products/42/?page=2`` -> ``https://shop.test/products/<int>/?page=``."""
    parts = urlsplit(url)
    path = "/".join(placeholder(s) or s for s in (parts.path or "/").split("/"))
    keys = sorted({key for key, _ in parse_qsl(parts.query, keep_blank_values=True)})
    query = "&".join(f"{key}=" for key in keys)
    return f"{parts.scheme}://{parts.netloc}{path}" + (f"?{query}" if query else "")


def origin(url: str) -> str:
    """``scheme://host:port`` with the default port left out."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port is None or port == _DEFAULT_PORTS.get(scheme):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def same_origin(url: str, other: str) -> bool:
    return origin(url) == origin(other)


def _is_tracking(key: str) -> bool:
    return key.lower().startswith("utm_") or key.lower() in TRACKING_PARAMETERS


def normalize_url(url: str, base: str | None = None) -> str | None:
    """The canonical form of a link: absolute, no fragment, no tracking parameters.

    ``..`` segments are resolved, the query is sorted and the host lowercased.
    ``None`` for links that are not web pages (``mailto:``, ``javascript:``...).
    """
    url = url.strip()
    if base is not None:
        url = urljoin(base, url)
    parts = urlsplit(url)
    if parts.scheme.lower() not in _DEFAULT_PORTS or not parts.hostname:
        return None
    path = parts.path or "/"
    trailing = path.endswith("/")
    path = posixpath.normpath(path)
    if path.startswith("//"):  # normpath keeps a leading double slash
        path = "/" + path.lstrip("/")
    if trailing and path != "/":
        path += "/"
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(key)
    )
    netloc = origin(url).split("://", 1)[1]
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query), ""))


def url_key(url: str) -> str:
    """Identity of a normalized URL: ``/a`` and ``/a/`` are one page."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def path_and_query(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
