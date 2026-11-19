"""Sitemap parsing (plain or gzipped XML) and URL normalisation.

Sitemaps are untrusted input, so XML is parsed with defusedxml (blocks entity-expansion
and external-entity attacks).
"""

from __future__ import annotations

import gzip
import io
import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from defusedxml.ElementTree import fromstring

from dgbot.scraping.models import SitemapEntry

_GZIP_MAGIC = b"\x1f\x8b"
_NS = re.compile(r"^\{[^}]*\}")
# Query parameters that only track campaigns; they never change page content.
_TRACKING_PARAMS = re.compile(r"^(utm_.*|gclid|fbclid|sfmc_.*|trk|ltclid|dealercode)$", re.I)
# Upper bound on a single decompressed sitemap (the protocol caps them at 50 MB).
_MAX_BYTES = 100 * 1024 * 1024


def _decompress(data: bytes) -> bytes:
    if not data.startswith(_GZIP_MAGIC):
        return data
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
        out = gz.read(_MAX_BYTES + 1)
    if len(out) > _MAX_BYTES:
        raise ValueError("sitemap larger than 100 MB after decompression")
    return out


def _local(tag: str) -> str:
    return _NS.sub("", tag)


def parse_sitemap(data: bytes) -> tuple[str, list[SitemapEntry]]:
    """Parse a sitemap or sitemap index.

    Returns `(kind, entries)` where kind is "urlset" or "sitemapindex".
    """
    root = fromstring(_decompress(data))
    kind = _local(root.tag)
    if kind not in {"urlset", "sitemapindex"}:
        raise ValueError(f"not a sitemap: root element <{kind}>")
    entries: list[SitemapEntry] = []
    for item in root:
        fields = {_local(child.tag): (child.text or "").strip() for child in item}
        if fields.get("loc"):
            entries.append(SitemapEntry(url=fields["loc"], lastmod=fields.get("lastmod") or None))
    return kind, entries


def normalize_url(url: str, *, force_host: str | None = None) -> str:
    """Canonical form for fetching and dedupe.

    - trims whitespace, forces https, lower-cases the host (optionally rewrites it)
    - drops fragments and tracking query params, sorts the remaining params
    - removes a trailing slash (except for the root)
    - **keeps path case**: servers may be case-sensitive (C-004)
    """
    parts = urlsplit(url.strip())
    host = (force_host or parts.netloc).lower()
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS.match(k))
    )
    return urlunsplit(("https", host, path, query, ""))


def dedupe(urls: Iterable[str]) -> list[str]:
    """Drop exact and case-insensitive duplicates, keeping the first spelling seen."""
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        key = url.lower()
        if key not in seen:
            seen.add(key)
            out.append(url)
    return out
