"""Raw store → processed snapshot (Phase 2). Offline only, re-runnable, no network.

    uv run python -m dgbot.scraping process

Parses every stored response, applies cross-record fixes (brand partners from partner
pages, duplicate projects, EN/AR listing links, hand-saved page details), then writes
`data/processed/` via `ingestion.snapshot` and a data-quality report.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from dgbot.core.errors import DgbotError
from dgbot.domain.models import AreaCoverage, Article, Listing, Page, Partner, Project
from dgbot.ingestion.snapshot import write_jsonl, write_manifest
from dgbot.scraping.sitemap import parse_sitemap
from dgbot.scraping.sources.darglobal.parsers import parse_page
from dgbot.scraping.sources.wasalt.parsers import (
    category_location,
    known_cities,
    listing_id_of,
    parse_category_url,
    parse_daily_url,
    parse_listing_page,
    parse_product_url,
)
from dgbot.scraping.storage import RawStore

logger = logging.getLogger(__name__)


@dataclass
class ProcessReport:
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ── DarGlobal ────────────────────────────────────────────────────────────────


@dataclass
class DarGlobalData:
    projects: list[Project]
    partners: list[Partner]
    articles: list[Article]
    pages: list[Page]


def process_darglobal(store: RawStore, report: ProcessReport) -> DarGlobalData:
    projects: list[Project] = []
    partners: list[Partner] = []
    articles: list[Article] = []
    pages: list[Page] = []
    for meta in store.iter_meta():
        if meta.kind in {"robots", "sitemap"}:
            continue
        try:
            record = parse_page(meta, store.load_body(meta).decode("utf-8"))
        except (DgbotError, KeyError, ValueError) as exc:
            report.errors.append(f"darglobal {meta.url}: {type(exc).__name__}: {exc}")
            continue
        if record is None:
            report.notes.append(f"darglobal {meta.url}: no text content — skipped")
        elif isinstance(record, Project):
            projects.append(record)
        elif isinstance(record, Partner):
            partners.append(record)
        elif isinstance(record, Article):
            articles.append(record)
        else:
            pages.append(record)

    projects = _assign_brands(_dedupe_projects(projects, report), partners)
    pages = _dedupe_pages(pages, report)
    return DarGlobalData(projects, partners, articles, pages)


def _completeness(model: BaseModel) -> int:
    return sum(1 for v in model.model_dump().values() if v not in (None, [], ""))


def _dedupe_projects(projects: list[Project], report: ProcessReport) -> list[Project]:
    """Same project under two URLs (e.g. Trump Tower Dubai) → keep the fuller record."""
    by_name: dict[str, list[Project]] = defaultdict(list)
    for project in projects:
        by_name[project.name.casefold()].append(project)
    kept = []
    for group in by_name.values():
        best = max(
            group,
            key=lambda p: (_completeness(p), p.updated_at or datetime.min.replace(tzinfo=UTC)),
        )
        kept.append(best)
        for other in group:
            if other is not best:
                report.notes.append(f"darglobal duplicate project {other.url} → kept {best.url}")
    return kept


def _dedupe_pages(pages: list[Page], report: ProcessReport) -> list[Page]:
    """Pages with identical body text (e.g. project-index pages listing the same catalogue)."""
    seen: dict[str, Page] = {}
    for page in sorted(pages, key=lambda p: len(p.url)):
        key = page.body.casefold()
        if key in seen:
            report.notes.append(
                f"darglobal duplicate page {page.url} → same text as {seen[key].url}"
            )
            continue
        seen[key] = page
    return list(seen.values())


def _assign_brands(projects: list[Project], partners: list[Partner]) -> list[Project]:
    """Brand partner from the partner pages' project lists, then by name mention."""
    by_url = {
        ref.url.lower(): partner.name for partner in partners for ref in partner.projects if ref.url
    }
    aliases = sorted(
        (
            (alias, p.name)
            for p in partners
            for alias in (p.name.casefold(), *_BRAND_ALIASES.get(p.name, ()))
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    out = []
    for project in projects:
        brand = by_url.get(project.url.lower())
        if brand is None:
            haystack = f"{project.name} {(project.description or '')[:300]}".casefold()
            brand = next(
                (
                    name
                    for alias, name in aliases
                    if re.search(rf"\b{re.escape(alias)}\b", haystack)
                ),
                project.brand_partner,  # e.g. "… by Mouawad" from the name itself
            )
        out.append(project.model_copy(update={"brand_partner": brand}))
    return out


# How project names refer to partners when they don't use the partner's full name.
_BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "The Trump Organization": ("trump",),
    "Automobili Lamborghini": ("lamborghini",),
    "W Hotels": ("w residences",),
}


# ── Wasalt ───────────────────────────────────────────────────────────────────


@dataclass
class WasaltData:
    listings: list[Listing]
    areas: list[AreaCoverage]


@dataclass
class _Sitemap:
    fetched_at: datetime
    entries: list[tuple[str, str | None]]  # (url, lastmod)


def _load_sitemaps(store: RawStore) -> dict[str, _Sitemap]:
    """`{"product:en": _Sitemap, ...}` from the stored Wasalt sitemaps."""
    out: dict[str, _Sitemap] = {}
    for meta in store.iter_meta():
        if meta.kind and meta.kind.startswith("sitemap:"):
            _, entries = parse_sitemap(store.load_body(meta))
            out[meta.kind.removeprefix("sitemap:")] = _Sitemap(
                meta.fetched_at, [(e.url, e.lastmod) for e in entries]
            )
    return out


def process_wasalt(store: RawStore, manual_dir: Path, report: ProcessReport) -> WasaltData:
    empty = _Sitemap(datetime.now(UTC), [])
    sitemaps = _load_sitemaps(store)

    listings: dict[str, Listing] = {}
    for kind, parser in (("product:en", parse_product_url), ("rental_pdp:en", parse_daily_url)):
        sitemap = sitemaps.get(kind, empty)
        broken = [url for url, _ in sitemap.entries if url.rstrip("/").endswith("/null")]
        if broken:  # Wasalt's own sitemap bug: literal ".../dailyrental/null" entries
            report.notes.append(f"wasalt {kind}: skipped {len(broken)} broken '/null' URLs")
        for url, lastmod in sitemap.entries:
            if url.rstrip("/").endswith("/null"):
                continue
            try:
                listing = parser(url, lastmod, sitemap.fetched_at)
            except DgbotError as exc:
                report.errors.append(f"wasalt {kind} {url}: {exc}")
                continue
            listings[listing.id] = listing

    linked = 0
    for kind, prefix in (("product:ar", "listing"), ("rental_pdp:ar", "daily")):
        for url, _ in sitemaps.get(kind, empty).entries:
            lid = listing_id_of(url)
            key = f"wasalt:{prefix}:{lid}"
            if lid and key in listings:
                listings[key] = listings[key].model_copy(update={"url_ar": url})
                linked += 1
    report.notes.append(f"wasalt: linked {linked} Arabic URLs to English listings by id")

    _merge_hand_saved(listings, manual_dir, report)

    category_urls = [
        (url, sitemap.fetched_at)
        for kind in ("category:en", "rental_srp:en")
        for sitemap in [sitemaps.get(kind, empty)]
        for url, _ in sitemap.entries
    ]
    cities = known_cities(loc for url, _ in category_urls if (loc := category_location(url)))
    areas: dict[str, AreaCoverage] = {}
    for url, fetched_at in category_urls:
        try:
            area = parse_category_url(url, cities, fetched_at)
        except DgbotError as exc:
            report.errors.append(f"wasalt category {url}: {exc}")
            continue
        areas[area.id] = area
    return WasaltData(list(listings.values()), list(areas.values()))


def _merge_hand_saved(
    listings: dict[str, Listing], manual_dir: Path, report: ProcessReport
) -> None:
    """Enrich sitemap listings with the pages Sehaj saved by hand (D-021).

    English pages override the slug-derived fields; Arabic pages become their own
    `lang="ar"` records (Arabic title/description for Arabic questions).
    """
    files = sorted(manual_dir.glob("*.html")) if manual_dir.exists() else []
    for path in files:
        saved_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        try:
            page = parse_listing_page(path.read_text(encoding="utf-8"), saved_at)
        except (DgbotError, KeyError, ValueError) as exc:
            report.errors.append(f"wasalt manual {path.name}: {type(exc).__name__}: {exc}")
            continue
        base = listings.get(f"wasalt:listing:{page.listing_id}")
        if page.lang.value == "ar":
            listings[page.id] = page
            if base:
                listings[base.id] = base.model_copy(update={"url_ar": page.url})
            continue
        if base is None:
            listings[page.id] = page
            continue
        updates = {k: v for k, v in page.model_dump().items() if v not in (None, "", [])}
        updates["area_inferred"] = page.area_sqm is None and base.area_inferred
        updates.pop("url_ar", None)
        listings[base.id] = base.model_copy(update=updates)
    report.notes.append(f"wasalt: merged {len(files)} hand-saved listing pages")


# ── quality report ───────────────────────────────────────────────────────────


def quality_report(groups: dict[str, Sequence[BaseModel]]) -> str:
    """Markdown: per record type, count and % of records with each field filled."""
    lines = ["# Data quality report", "", f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC.", ""]
    for name, records in groups.items():
        lines += [f"## {name} — {len(records)} records", ""]
        if not records:
            continue
        fields = [
            f for f in type(records[0]).model_fields if f not in {"source", "lang", "scraped_at"}
        ]
        filled = Counter(f for r in records for f in fields if getattr(r, f) not in (None, [], ""))
        lines += ["| field | filled |", "|---|---|"]
        lines += [f"| `{f}` | {filled[f] / len(records):.0%} |" for f in fields]
        lines.append("")
    return "\n".join(lines)


def _breakdown(records: Iterable[BaseModel], attr: str) -> str:
    counts = Counter(str(getattr(r, attr)) for r in records)
    return ", ".join(f"{k} {v}" for k, v in counts.most_common(12))


# ── entry point ──────────────────────────────────────────────────────────────


def run(raw_root: Path, out_root: Path) -> ProcessReport:
    report = ProcessReport()
    dg = process_darglobal(RawStore(raw_root, "darglobal"), report)
    ws = process_wasalt(RawStore(raw_root, "wasalt"), raw_root / "wasalt" / "manual", report)
    sample = [lst for lst in ws.listings if lst.detail == "page"]

    outputs: dict[str, Sequence[BaseModel]] = {
        "darglobal/projects.jsonl": dg.projects,
        "darglobal/partners.jsonl": dg.partners,
        "darglobal/articles.jsonl": dg.articles,
        "darglobal/pages.jsonl": dg.pages,
        "wasalt/listings.jsonl.gz": ws.listings,
        "wasalt/areas.jsonl.gz": ws.areas,
        "wasalt/sample_listings.jsonl": sample,
    }
    for rel, records in outputs.items():
        report.counts[rel] = write_jsonl(out_root / rel, records)

    fetched = [
        m.fetched_at
        for source in ("darglobal", "wasalt")
        for m in RawStore(raw_root, source).iter_meta()
    ]
    write_manifest(out_root, report.counts, (min(fetched), max(fetched)))

    md = quality_report(
        {
            "DarGlobal projects": dg.projects,
            "DarGlobal partners": dg.partners,
            "DarGlobal articles": dg.articles,
            "DarGlobal pages": dg.pages,
            "Wasalt listings (all)": ws.listings,
            "Wasalt listings (hand-saved sample)": sample,
            "Wasalt area coverage": ws.areas,
        }
    )
    md += "\n## Breakdowns\n\n"
    md += f"- Projects by country: {_breakdown(dg.projects, 'country')}\n"
    md += f"- Articles by kind: {_breakdown(dg.articles, 'kind')}\n"
    md += f"- Pages by kind: {_breakdown(dg.pages, 'kind')}\n"
    md += f"- Listings by purpose: {_breakdown(ws.listings, 'purpose')}\n"
    md += f"- Listings by type: {_breakdown(ws.listings, 'property_type')}\n"
    md += f"- Areas by city (top 12): {_breakdown(ws.areas, 'city')}\n"
    inferred = sum(1 for lst in ws.listings if lst.area_inferred)
    md += f"- Listing areas repaired from slugs (C-011): {inferred}\n"
    md += f"\n## Parse errors ({len(report.errors)})\n\n" + "".join(
        f"- {e}\n" for e in report.errors[:50]
    )
    md += f"\n## Notes ({len(report.notes)})\n\n" + "".join(f"- {n}\n" for n in report.notes)
    (out_root / "QUALITY.md").write_text(md, encoding="utf-8")
    return report
