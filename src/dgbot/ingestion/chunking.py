"""Records → retrievable chunks (Phase 3, D-038). Pure functions: no I/O, no models.

Shapes, chosen per record type:
- Project  → a **card** (name, location, type, status, units, facts) + details (description,
  location, amenities, highlights) + one chunk **per FAQ** (already question-shaped).
- Partner  → one card.
- Article / Page → paragraph-aware windows of ~`chunk_words` with overlap, title-prefixed.
- Wasalt   → *not* one chunk per listing (D-018: 60k near-identical rows would drown
  DarGlobal). Instead: generated **summaries** (overview, per purpose x type stats, per
  city x purpose coverage) + full cards for the hand-saved listings. Exact counts/filters
  go to SQLite (Phase 4 tool).
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, Final

from dgbot.domain.models import (
    AnyRecord,
    AreaCoverage,
    Article,
    Chunk,
    Lang,
    Listing,
    Page,
    Partner,
    Project,
    Source,
)
from dgbot.domain.places import CITY_AR

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_PURPOSE_LABEL: Final = {"sale": "for sale", "rent": "for rent", "daily_rent": "for daily rental"}
_MAX_DISTRICTS_PER_CHUNK: Final = 60

# Arabic terms for the bilingual Wasalt summaries (D-042). Wasalt is a Saudi portal and
# users ask in Arabic; the only other Arabic text in the index is 3 hand-saved listings,
# so without these an Arabic question gravitates to those cards (C-017).
WASALT_AR: Final = "وصلت"
DARGLOBAL_AR: Final = "دار جلوبال"
_PURPOSE_AR: Final = {"sale": "للبيع", "rent": "للإيجار", "daily_rent": "للإيجار اليومي"}
_TYPE_AR: Final = {
    "apartment": "شقق",
    "villa": "فلل",
    "land": "أراضي",
    "floor": "أدوار",
    "building": "عمارات",
    "rest house": "استراحات",
    "chalet": "شاليهات",
    "room": "غرف",
    "studio": "استوديوهات",
    "duplex": "دوبلكس",
    "farm": "مزارع",
    "commercial property": "عقارات تجارية",
    "property": "عقارات",
}


def build_chunks(
    records: Iterable[AnyRecord], *, chunk_words: int = 200, overlap_words: int = 40
) -> list[Chunk]:
    """All chunks for a snapshot, deterministic order (by chunk id)."""
    chunks: list[Chunk] = []
    listings: list[Listing] = []
    areas: list[AreaCoverage] = []
    seen: set[str] = set()
    for record in records:
        if record.id in seen:  # sample_listings.jsonl repeats the hand-saved listings
            continue
        seen.add(record.id)
        if isinstance(record, Project):
            chunks += chunk_project(record)
        elif isinstance(record, Partner):
            chunks += chunk_partner(record)
        elif isinstance(record, Article):
            chunks += chunk_article(record, chunk_words, overlap_words)
        elif isinstance(record, Page):
            chunks += chunk_page(record, chunk_words, overlap_words)
        elif isinstance(record, Listing):
            listings.append(record)
            if record.detail == "page":
                chunks.append(chunk_listing_card(record))
        elif isinstance(record, AreaCoverage):
            areas.append(record)
    chunks += wasalt_summaries(listings, areas)
    ids = [c.id for c in chunks]
    duplicates = {i for i in ids if ids.count(i) > 1} if len(ids) != len(set(ids)) else set()
    if duplicates:
        raise ValueError(f"duplicate chunk ids: {sorted(duplicates)[:5]}")
    return sorted(chunks, key=lambda c: c.id)


# ── text windows ─────────────────────────────────────────────────────────────


def split_words(text: str, chunk_words: int, overlap_words: int) -> list[str]:
    """Paragraph-aware windows: pack whole paragraphs up to `chunk_words`; split only
    paragraphs that are themselves too long; carry `overlap_words` into the next window."""
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
    pieces: list[list[str]] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        step = max(chunk_words - overlap_words, 1)
        if len(words) <= chunk_words:
            pieces.append(words)
        else:
            pieces += [words[i : i + chunk_words] for i in range(0, len(words), step)]
    windows: list[list[str]] = []
    current: list[str] = []
    for piece in pieces:
        if current and len(current) + len(piece) > chunk_words:
            windows.append(current)
            current = current[-overlap_words:] if overlap_words else []
        current = current + piece
    if current and (not windows or current != windows[-1][-len(current) :]):
        windows.append(current)
    return [" ".join(w) for w in windows]


def _chunk(
    record: Project | Partner | Article | Page | Listing,
    section: str,
    n: int,
    title: str,
    text: str,
    **meta: Any,
) -> Chunk:
    return Chunk(
        id=f"{record.id}#{section}-{n}",
        record_id=record.id,
        record_type=record.record_type,
        section=section,
        source=record.source,
        lang=record.lang,
        url=record.url,
        title=title,
        text=text.strip(),
        **meta,
    )


def _lines(*pairs: tuple[str, object]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in pairs if v not in (None, "", []))


# ── DarGlobal ────────────────────────────────────────────────────────────────


def chunk_project(p: Project) -> list[Chunk]:
    meta = {"country": p.country, "city": p.city, "kind": "project"}
    card = "\n".join(
        filter(
            None,
            [
                f"{p.name} — DarGlobal project ({DARGLOBAL_AR})",
                _lines(
                    ("Location", p.location),
                    ("Country", p.country),
                    ("Brand partner", p.brand_partner),
                    ("Property type", p.property_type),
                    ("Status", p.status),
                    ("Unit types", p.unit_types),
                ),
                _lines(
                    *((f.name, f.value) for f in p.facts if not _shown_on_card(f.name, f.value, p))
                ),
                "Prices are not published by DarGlobal for this project.",
            ],
        )
    )
    chunks = [_chunk(p, "card", 0, p.name, card, **meta)]
    details = "\n\n".join(
        filter(
            None,
            [
                f"{p.name} — overview",
                p.description,
                f"Location: {p.location_description}" if p.location_description else None,
                "Amenities: " + ", ".join(p.amenities) if p.amenities else None,
                "Highlights:\n" + "\n".join(f"- {h}" for h in p.highlights)
                if p.highlights
                else None,
                "Nearby: " + ", ".join(p.nearby) if p.nearby else None,
            ],
        )
    )
    chunks.append(_chunk(p, "details", 0, p.name, details, **meta))
    if p.other_text:
        chunks.append(
            _chunk(p, "more", 0, p.name, f"{p.name} — more details\n\n{p.other_text}", **meta)
        )
    chunks += [
        _chunk(p, "faq", i, p.name, f"{p.name} — FAQ\nQ: {f.question}\nA: {f.answer}", **meta)
        for i, f in enumerate(p.faqs)
    ]
    return chunks


_CARD_FACT_NAMES: Final = frozenset(
    {"location", "property type", "project type", "status", "stage", "unit type", "country"}
)


def _shown_on_card(name: str, value: str, p: Project) -> bool:
    """Facts already rendered as card fields (avoid 'Location' twice)."""
    return name.strip().casefold() in _CARD_FACT_NAMES or value in {
        p.location,
        p.status,
        p.property_type,
        p.unit_types,
    }


def chunk_partner(p: Partner) -> list[Chunk]:
    projects = "; ".join(
        f"{ref.name}" + (f" ({ref.location})" if ref.location else "") for ref in p.projects
    )
    text = "\n".join(
        filter(
            None,
            [
                f"{p.name} — DarGlobal brand partner",
                p.tagline,
                p.description,
                f"Projects with {p.name}: {projects}" if projects else None,
            ],
        )
    )
    return [_chunk(p, "card", 0, p.name, text, kind="partner")]


def chunk_article(a: Article, chunk_words: int, overlap_words: int) -> list[Chunk]:
    label = {
        "blog": "DarGlobal blog",
        "press": "DarGlobal press release",
        "insight": "DarGlobal insight",
    }[a.kind]
    header = f"{a.title} — {label}" + (f" ({a.published.isoformat()})" if a.published else "")
    if a.dateline:
        header += f", {a.dateline}"
    return [
        _chunk(a, "body", i, a.title, f"{header}\n\n{window}", kind=a.kind, published=a.published)
        for i, window in enumerate(split_words(a.body, chunk_words, overlap_words))
    ]


def chunk_page(p: Page, chunk_words: int, overlap_words: int) -> list[Chunk]:
    header = f"{p.title} — DarGlobal" + (" project" if p.kind == "project" else " page")
    chunks = [
        _chunk(p, "body", i, p.title, f"{header}\n\n{window}", kind=p.kind)
        for i, window in enumerate(split_words(p.body, chunk_words, overlap_words))
    ]
    chunks += [
        _chunk(
            p, "faq", i, p.title, f"{p.title} — FAQ\nQ: {f.question}\nA: {f.answer}", kind=p.kind
        )
        for i, f in enumerate(p.faqs)
    ]
    return chunks


# ── Wasalt ───────────────────────────────────────────────────────────────────


def chunk_listing_card(lst: Listing) -> Chunk:
    """A hand-saved listing with real price/location (detail="page")."""
    price = None
    if lst.price is not None:
        price = f"{lst.price:,.0f} {lst.currency or ''}".strip()
        if lst.price_period:
            price += f" ({lst.price_period})"
    area = f"{lst.area_sqm:g} sqm" if lst.area_sqm else None
    where = ", ".join(filter(None, [lst.district, lst.zone, lst.city]))
    title = lst.title or f"{lst.property_type} {_PURPOSE_LABEL[lst.purpose]}"
    text = "\n".join(
        filter(
            None,
            [
                f"{title} — Wasalt listing {lst.listing_id}"
                + (" (Arabic page)" if lst.lang is Lang.AR else ""),
                _lines(
                    ("Purpose", _PURPOSE_LABEL[lst.purpose]),
                    ("Property type", lst.property_type),
                    ("Price", price),
                    ("Location", where),
                    ("Area", area),
                    ("Bedrooms", lst.bedrooms),
                    ("Bathrooms", lst.bathrooms),
                    ("Facing", lst.facing),
                    ("Street width", f"{lst.street_width_m} m" if lst.street_width_m else None),
                    ("Furnishing", lst.furnishing),
                    ("Listed", lst.listed_at),
                ),
                lst.description,
            ],
        )
    )
    return _chunk(
        lst,
        "card",
        0,
        title,
        text,
        city=lst.city,
        purpose=lst.purpose,
        property_type=lst.property_type,
    )


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _summary(sid: str, title: str, text: str, url: str, **meta: Any) -> Chunk:
    return Chunk(
        id=f"wasalt:summary:{sid}#summary-0",
        record_id=f"wasalt:summary:{sid}",
        record_type="summary",
        section="summary",
        source=Source.WASALT,
        url=url,
        title=title,
        text=text,
        **meta,
    )


def _plural(kind: str) -> str:
    return {"property": "properties", "commercial property": "commercial properties"}.get(
        kind, kind if kind.endswith("s") else kind + "s"
    )


def wasalt_summaries(listings: Sequence[Listing], areas: Sequence[AreaCoverage]) -> list[Chunk]:
    """Generated, data-backed summaries — the only Wasalt bulk data in the vector index."""
    if not listings and not areas:
        return []
    chunks: list[Chunk] = []
    english = [lst for lst in listings if lst.lang is Lang.EN]
    by_purpose = Counter(lst.purpose for lst in english)
    by_type = Counter((lst.purpose, lst.property_type) for lst in english)
    cities = sorted({a.city for a in areas})
    overview = "\n".join(
        [
            f"Wasalt (wasalt.sa, {WASALT_AR}) — overview: how many listings Wasalt has",
            f"Wasalt has {len(english):,} property listings in this dataset "
            + "("
            + ", ".join(f"{n:,} {_PURPOSE_LABEL[p]}" for p, n in by_purpose.most_common())
            + ").",
            "Most common: "
            + ", ".join(
                f"{n:,} {_plural(t)} {_PURPOSE_LABEL[p]}" for (p, t), n in by_type.most_common(8)
            )
            + ".",
            f"Wasalt lists properties in {len(cities)} Saudi cities and towns, including "
            + ", ".join(c for c, _ in Counter(a.city for a in areas).most_common(15))
            + ".",
            "Data source: Wasalt's public sitemaps. Most listings include type, size, bedrooms "
            "and listing id but not price or city; prices are known only for a small "
            "hand-saved sample.",
            f"بالعربية: عدد العقارات المعروضة على منصة {WASALT_AR}: {len(english):,} عقار "
            f"(للبيع {by_purpose.get('sale', 0):,}، للإيجار {by_purpose.get('rent', 0):,}، "
            f"للإيجار اليومي {by_purpose.get('daily_rent', 0):,}).",
        ]
    )
    chunks.append(_summary("overview", "Wasalt overview", overview, "https://wasalt.sa/en"))

    for (purpose, kind), count in sorted(by_type.items()):
        if count < 20:
            continue
        group = [lst for lst in english if lst.purpose == purpose and lst.property_type == kind]
        areas_sqm = [lst.area_sqm for lst in group if lst.area_sqm]
        beds = Counter(lst.bedrooms for lst in group if lst.bedrooms)
        facing = Counter(lst.facing for lst in group if lst.facing)
        lines = [
            f"Wasalt — {_plural(kind)} {_PURPOSE_LABEL[purpose]}: statistics",
            f"Number of listings: {count:,}.",
        ]
        if len(areas_sqm) >= 10:
            q = statistics.quantiles(areas_sqm, n=4)
            lines.append(
                f"Size: median {statistics.median(areas_sqm):,.0f} sqm; middle half between "
                f"{q[0]:,.0f} and {q[2]:,.0f} sqm (sizes from listing URLs, some approximate)."
            )
        if beds:
            total = sum(beds.values())
            mix = ", ".join(
                f"{b} bedroom{'s' if b != 1 else ''} {n / total:.0%}"
                for b, n in sorted(beds.most_common(6))
            )
            lines.append(f"Bedrooms ({total:,} listings state them): {mix}.")
        if facing:
            lines.append(
                "Facing: " + ", ".join(f"{f} {n:,}" for f, n in facing.most_common(4)) + "."
            )
        lines.append("Prices are not available for these listings (sitemap data only).")
        lines.append(
            f"بالعربية: {_TYPE_AR.get(kind, kind)} {_PURPOSE_AR[purpose]} على {WASALT_AR}: "
            f"{count:,} عقار."
        )
        chunks.append(
            _summary(
                f"type:{purpose}:{_slugify(kind)}",
                f"Wasalt {_plural(kind)} {_PURPOSE_LABEL[purpose]}",
                "\n".join(lines),
                "https://wasalt.sa/en",
                purpose=purpose,
                property_type=kind,
            )
        )

    grouped: dict[tuple[str, str], list[AreaCoverage]] = defaultdict(list)
    for area in areas:
        grouped[(area.city, area.purpose)].append(area)
    for (city, area_purpose), area_group in sorted(grouped.items()):
        districts = sorted({a.district for a in area_group if a.district})
        zones = sorted({a.zone for a in area_group if a.zone})
        types = Counter(a.property_type for a in area_group if a.property_type != "property")
        root = next(
            (a.url for a in area_group if a.district is None and a.property_type == "property"),
            area_group[0].url,
        )
        for part in range(max(1, -(-len(districts) // _MAX_DISTRICTS_PER_CHUNK))):
            names = districts[
                part * _MAX_DISTRICTS_PER_CHUNK : (part + 1) * _MAX_DISTRICTS_PER_CHUNK
            ]
            lines = [
                f"Wasalt — properties {_PURPOSE_LABEL[area_purpose]} in {city}"
                + (f" (part {part + 1})" if len(districts) > _MAX_DISTRICTS_PER_CHUNK else ""),
                f"Wasalt has listings {_PURPOSE_LABEL[area_purpose]} in {city}"
                + (f" across {len(districts)} districts" if districts else "")
                + ".",
            ]
            city_ar = CITY_AR.get(city)
            types_ar = "، ".join(dict.fromkeys(_TYPE_AR.get(t, t) for t, _ in types.most_common(6)))
            lines.append(
                f"بالعربية: عقارات {_PURPOSE_AR[area_purpose]} في {city_ar or city} على {WASALT_AR}"
                + (f" ({types_ar})" if types_ar else "")
                + "."
            )
            if zones:
                lines.append(f"Zones: {', '.join(zones)}.")
            if types:
                lines.append(
                    "Property types listed: "
                    + ", ".join(_plural(t) for t, _ in types.most_common(10))
                    + "."
                )
            if names:
                lines.append(
                    ("Districts include: " if part == 0 else "More districts: ")
                    + ", ".join(names)
                    + "."
                )
            chunks.append(
                _summary(
                    f"city:{_slugify(city)}:{area_purpose}" + (f":{part}" if part else ""),
                    f"Wasalt properties {_PURPOSE_LABEL[area_purpose]} in {city}",
                    "\n".join(lines),
                    root,
                    city=city,
                    purpose=area_purpose,
                )
            )
    return chunks
