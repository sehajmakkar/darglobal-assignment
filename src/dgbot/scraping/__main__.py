"""Scraping CLI (offline only, D-003).

    uv run python -m dgbot.scraping wasalt              # CDN sitemaps (automated)
    uv run python -m dgbot.scraping darglobal --limit 5 # headed browser (D-020), trial run
    uv run python -m dgbot.scraping all

Re-runs are incremental: cached URLs are skipped unless `--refresh`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from dgbot.core.config import get_settings
from dgbot.core.logging import configure_logging
from dgbot.scraping.models import CollectReport
from dgbot.scraping.sources.base import Source
from dgbot.scraping.sources.darglobal.source import DarGlobalBrowserSource
from dgbot.scraping.sources.wasalt.source import WasaltSitemapSource
from dgbot.scraping.storage import RawStore

SOURCES: dict[str, type[Source]] = {
    "wasalt": WasaltSitemapSource,
    "darglobal": DarGlobalBrowserSource,
}

logger = logging.getLogger("dgbot.scraping")


async def _run(names: list[str], limit: int | None, refresh: bool) -> list[CollectReport]:
    settings = get_settings()
    reports = []
    for name in names:
        source = SOURCES[name]()
        store = RawStore(settings.raw_data_dir, source.name)
        logger.info("collecting %s → %s", name, store.dir)
        reports.append(await source.collect(settings, store, limit=limit, refresh=refresh))
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m dgbot.scraping", description=__doc__)
    parser.add_argument("source", choices=[*SOURCES, "all"])
    parser.add_argument("--limit", type=int, default=None, help="max new fetches per source")
    parser.add_argument("--refresh", action="store_true", help="re-fetch cached URLs")
    args = parser.parse_args(argv)

    configure_logging(get_settings())
    names = list(SOURCES) if args.source == "all" else [args.source]
    reports = asyncio.run(_run(names, args.limit, args.refresh))
    for report in reports:
        print(report.model_dump_json(indent=2))
    return 1 if any(r.stopped_reason or r.failed for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
