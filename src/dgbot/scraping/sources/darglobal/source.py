"""DarGlobal collector: a standard, headed Chromium at human pace (D-020).

Every DarGlobal URL serves an Imperva Incapsula JS check to plain HTTP clients (C-003),
so this collector drives a real browser. Rules, from D-020:
- standard Playwright Chromium, **headed**, its own User-Agent left as is
- no stealth plugins, no proxies, no CAPTCHA solving
- one page at a time, `scraper_browser_delay_s` (3-10 s) apart
- robots.txt (read through the same browser) is obeyed
- the first challenge/block page **stops the run**; we never retry around it
Every response is cached, so re-runs only fetch what's missing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Response, async_playwright

from dgbot.core.config import Settings
from dgbot.scraping.models import CollectReport
from dgbot.scraping.robots import RobotsPolicy
from dgbot.scraping.sitemap import dedupe, normalize_url, parse_sitemap
from dgbot.scraping.sources.darglobal.urls import (
    is_challenge_page,
    is_on_site,
    plan_fetch_order,
)
from dgbot.scraping.storage import RawStore

logger = logging.getLogger(__name__)

HOST: Final = "darglobal.co.uk"
ROBOTS_URL: Final = f"https://{HOST}/robots.txt"
# robots.txt's own `Sitemap:` line points at the bare domain (broken); this is the real one.
SITEMAP_URL: Final = f"https://{HOST}/sitemap.xml"
_NAV_TIMEOUT_MS: Final = 60_000
# Short pause after DOMContentLoaded for client hydration before snapshotting the DOM.
_SETTLE_MS: Final = 1_500


class DarGlobalBrowserSource:
    name = "darglobal"

    async def collect(
        self, settings: Settings, store: RawStore, *, limit: int | None, refresh: bool
    ) -> CollectReport:
        report = CollectReport(source=self.name)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            try:
                page = await browser.new_page()
                logger.info("browser UA: %s", await page.evaluate("navigator.userAgent"))
                await self._run(page, settings, store, report, limit=limit, refresh=refresh)
            finally:
                await browser.close()
        return report

    async def _run(
        self,
        page: Page,
        settings: Settings,
        store: RawStore,
        report: CollectReport,
        *,
        limit: int | None,
        refresh: bool,
    ) -> None:
        delay = settings.scraper_browser_delay_s

        robots_body = await self._fetch_raw(page, ROBOTS_URL, store, kind="robots", refresh=True)
        if robots_body is None:
            report.stopped_reason = "robots.txt not readable (challenge or error)"
            return
        policy = RobotsPolicy.from_text(robots_body.decode(), settings.scraper_user_agent)
        await asyncio.sleep(delay)

        sitemap_body = await self._fetch_raw(
            page, SITEMAP_URL, store, kind="sitemap", refresh=refresh
        )
        if sitemap_body is None:
            report.stopped_reason = "sitemap.xml not readable (challenge or error)"
            return
        _, entries = parse_sitemap(sitemap_body)
        urls = dedupe(normalize_url(e.url, force_host=HOST) for e in entries)
        report.discovered = len(urls)
        plan = plan_fetch_order(urls)
        report.skipped = len(urls) - len(plan)

        for index, (url, kind) in enumerate(plan, start=1):
            if not policy.allowed(url):
                logger.info("robots.txt disallows %s — skipping", url)
                report.skipped += 1
                continue
            if store.has(url) and not refresh:
                report.cached += 1
                continue
            if limit is not None and report.fetched >= limit:
                report.skipped += 1
                continue
            await asyncio.sleep(delay)
            outcome = await self._fetch_page(page, url, store, kind=str(kind))
            if outcome == "blocked":
                report.stopped_reason = f"bot check shown at {url} — stopped (D-020 boundary)"
                logger.error(report.stopped_reason)
                return
            if outcome == "ok":
                report.fetched += 1
            else:
                report.failed.append(f"{url} ({outcome})")
            logger.info("[%d/%d] %-8s %-13s %s", index, len(plan), outcome, kind, url)

    async def _fetch_raw(
        self, page: Page, url: str, store: RawStore, *, kind: str, refresh: bool
    ) -> bytes | None:
        """robots.txt / sitemap: keep the raw response body, not the rendered DOM."""
        if store.has(url) and not refresh:
            return store.load_body(store.load_meta(url))
        response = await page.goto(url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
        if response is None or not response.ok:
            return None
        body = await response.body()
        if is_challenge_page(body.decode(errors="replace")):
            return None
        suffix = ".txt" if kind == "robots" else ".xml"
        self._save(store, url, body, response, suffix=suffix, kind=kind)
        return body

    async def _fetch_page(self, page: Page, url: str, store: RawStore, *, kind: str) -> str:
        """Returns "ok", "blocked", or a short failure reason."""
        try:
            # The site is server-rendered Next.js: content + __NEXT_DATA__ are complete at
            # DOMContentLoaded. "networkidle" never settles (trackers) and "load" never
            # fires on some pages (heavy media) — both just time out (C-010).
            response = await page.goto(url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
            await page.wait_for_timeout(_SETTLE_MS)
            html = await page.content()
        except PlaywrightError as exc:  # navigation failed or timed out: record it, move on
            return f"error: {type(exc).__name__}"
        if is_challenge_page(html):
            return "blocked"
        if response is None:
            return "error: no response"
        if response.status >= 400:
            return f"HTTP {response.status}"  # not cached → retried on the next run
        if not is_on_site(page.url):
            return f"redirected off-site to {page.url}"  # never store other domains
        self._save(store, url, html.encode(), response, suffix=".html", kind=kind)
        return "ok"

    @staticmethod
    def _save(
        store: RawStore, url: str, body: bytes, response: Response, *, suffix: str, kind: str
    ) -> None:
        store.save(
            url,
            body,
            status=response.status,
            final_url=response.url,
            content_type=response.headers.get("content-type"),
            suffix=suffix,
            method="browser",
            kind=kind,
        )
