"""Scraping CLI (offline only, D-003).

    uv run python -m dgbot.scraping collect wasalt              # CDN sitemaps (automated)
    uv run python -m dgbot.scraping collect darglobal --limit 5 # headed browser (D-020)
    uv run python -m dgbot.scraping collect all
    uv run python -m dgbot.scraping process                     # raw → data/processed

Collection is incremental: cached URLs are skipped unless `--refresh`.
Processing reads only the local raw store — no network.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from dgbot.core.config import get_settings
from dgbot.core.logging import configure_logging
from dgbot.scraping.models import CollectReport
from dgbot.scraping.process import run as run_process
from dgbot.scraping.sources.base import Source
from dgbot.scraping.sources.darglobal.source import DarGlobalBrowserSource
from dgbot.scraping.sources.wasalt.source import WasaltSitemapSource
from dgbot.scraping.storage import RawStore

SOURCES: dict[str, type[Source]] = {
    "wasalt": WasaltSitemapSource,
    "darglobal": DarGlobalBrowserSource,
}

logger = logging.getLogger("dgbot.scraping")


async def _collect(names: list[str], limit: int | None, refresh: bool) -> list[CollectReport]:
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
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="fetch raw pages/sitemaps into data/raw")
    collect.add_argument("source", choices=[*SOURCES, "all"])
    collect.add_argument("--limit", type=int, default=None, help="max new fetches per source")
    collect.add_argument("--refresh", action="store_true", help="re-fetch cached URLs")
    commands.add_parser("process", help="parse data/raw into the data/processed snapshot")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings)

    if args.command == "process":
        report = run_process(settings.raw_data_dir, settings.processed_data_dir)
        for path, count in report.counts.items():
            print(f"{count:>7}  {settings.processed_data_dir / path}")
        print(f"errors: {len(report.errors)}  notes: {len(report.notes)}  (see QUALITY.md)")
        return 1 if report.errors else 0

    names = list(SOURCES) if args.source == "all" else [args.source]
    reports = asyncio.run(_collect(names, args.limit, args.refresh))
    for collect_report in reports:
        print(collect_report.model_dump_json(indent=2))
    return 1 if any(r.stopped_reason or r.failed for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
