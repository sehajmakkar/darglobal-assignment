import gzip
from pathlib import Path

import httpx

from dgbot.core.config import Settings
from dgbot.scraping.http import PoliteClient
from dgbot.scraping.sources.wasalt.source import WasaltSitemapSource, sitemap_urls
from dgbot.scraping.storage import RawStore


async def _no_sleep(_: float) -> None:
    return None


def _sitemap(n: int) -> bytes:
    urls = "".join(
        f"<url><loc>https://wasalt.sa/en/property/sale/x-{i}</loc></url>" for i in range(n)
    )
    return gzip.compress(f"<urlset>{urls}</urlset>".encode())


def test_ten_sitemaps_all_on_the_cdn() -> None:
    urls = [url for _, url in sitemap_urls()]

    assert len(urls) == 10
    assert all(url.startswith("https://cdn.wasalt.sa/sitemap/") for url in urls)
    assert all(url.endswith("_sa.xml.gz") for url in urls)


async def test_collects_sitemaps_only_from_the_cdn_and_caches_them(tmp_path: Path) -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=_sitemap(3))

    settings = Settings(_env_file=None, scraper_max_rps=2.0)
    store = RawStore(tmp_path, "wasalt")

    def make_client() -> PoliteClient:
        return PoliteClient(settings, transport=httpx.MockTransport(handler), sleep=_no_sleep)

    first = await WasaltSitemapSource(make_client()).collect(
        settings, store, limit=None, refresh=False
    )
    assert (first.fetched, first.cached, first.discovered) == (10, 0, 30)
    assert set(hosts) == {"cdn.wasalt.sa"}  # never wasalt.sa itself (D-021)

    hosts.clear()
    second = await WasaltSitemapSource(make_client()).collect(
        settings, store, limit=None, refresh=False
    )
    assert (second.fetched, second.cached, second.discovered) == (0, 10, 30)
    assert hosts == []  # fully served from the cache
