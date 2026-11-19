"""Wasalt collector: public CDN sitemaps only (D-021).

`wasalt.sa` itself answers automated clients with a Cloudflare 403 (C-001), so this
collector never requests it. Listing pages come only from Sehaj's hand-saved sample
(`data/raw/wasalt/manual/`), which this module does not touch.
"""

from __future__ import annotations

import logging
from typing import Final
from urllib.parse import urlsplit

from dgbot.core.config import Settings
from dgbot.core.errors import DgbotError
from dgbot.scraping.http import PoliteClient
from dgbot.scraping.models import CollectReport
from dgbot.scraping.sitemap import parse_sitemap
from dgbot.scraping.storage import RawStore

logger = logging.getLogger(__name__)

CDN: Final = "https://cdn.wasalt.sa/sitemap"
ALLOWED_HOSTS: Final = frozenset({"cdn.wasalt.sa"})
# What each sitemap holds (recon 2026-11-19, notes/recon.md).
SITEMAP_KINDS: Final = ("product", "category", "rental_pdp", "rental_srp", "static")
LANGS: Final = ("en", "ar")


def sitemap_urls() -> list[tuple[str, str]]:
    """`(kind, url)` for all 10 sitemaps, English first."""
    return [
        (f"{kind}:{lang}", f"{CDN}/{kind}_sitemap_{lang}_sa.xml.gz")
        for kind in SITEMAP_KINDS
        for lang in LANGS
    ]


class WasaltSitemapSource:
    name = "wasalt"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self._client = client  # injected in tests

    async def collect(
        self, settings: Settings, store: RawStore, *, limit: int | None, refresh: bool
    ) -> CollectReport:
        report = CollectReport(source=self.name)
        client = self._client or PoliteClient(settings)
        async with client:
            for kind, url in sitemap_urls():
                if urlsplit(url).netloc not in ALLOWED_HOSTS:  # defence in depth (D-021)
                    raise AssertionError(f"refusing to fetch non-CDN Wasalt URL: {url}")
                if store.has(url) and not refresh:
                    report.cached += 1
                    body = store.load_body(store.load_meta(url))
                elif limit is not None and report.fetched >= limit:
                    report.skipped += 1
                    continue
                else:
                    try:
                        response = await client.get(url)
                    except DgbotError as exc:
                        logger.error("failed %s: %s", url, exc)
                        report.failed.append(url)
                        continue
                    if not response.is_success:
                        report.failed.append(f"{url} (HTTP {response.status_code})")
                        continue
                    body = response.content
                    store.save(
                        url,
                        body,
                        status=response.status_code,
                        final_url=str(response.url),
                        content_type=response.headers.get("content-type"),
                        suffix=".xml.gz",
                        kind=f"sitemap:{kind}",
                    )
                    report.fetched += 1
                _, entries = parse_sitemap(body)
                report.discovered += len(entries)
                logger.info("%-16s %6d URLs  %s", kind, len(entries), url)
        return report
