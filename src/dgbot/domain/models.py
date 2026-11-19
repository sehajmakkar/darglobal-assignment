"""Domain records: the shape of the processed snapshot (`data/processed/`).

Pure data, no I/O. Produced offline by the scraping layer's parsers, consumed by
ingestion (chunking/indexing) and, later, the chat layer for citations. Records only
ever hold fields we chose to keep (allow-list, D-019) — never raw CMS blobs.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Source(StrEnum):
    DARGLOBAL = "darglobal"
    WASALT = "wasalt"


class Lang(StrEnum):
    EN = "en"
    AR = "ar"


class _Record(BaseModel):
    """Fields every record has. `id` is stable across re-scrapes."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source: Source
    url: str
    lang: Lang = Lang.EN
    scraped_at: datetime


class Fact(BaseModel):
    """A labelled fact as the site shows it, e.g. ("Status", "Under construction")."""

    model_config = ConfigDict(extra="forbid")
    name: str
    value: str


class Faq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    answer: str


class ProjectRef(BaseModel):
    """A link from one record to a DarGlobal project (e.g. partner → its projects)."""

    model_config = ConfigDict(extra="forbid")
    name: str
    url: str | None = None
    location: str | None = None


# ── DarGlobal ────────────────────────────────────────────────────────────────


class Project(_Record):
    """A DarGlobal development built on the standard project template."""

    record_type: Literal["project"] = "project"
    name: str
    location: str | None = None
    city: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    brand_partner: str | None = None
    property_type: str | None = None
    status: str | None = None
    unit_types: str | None = None
    facts: list[Fact] = Field(default_factory=list)
    description: str | None = None
    location_description: str | None = None
    amenities: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    nearby: list[str] = Field(default_factory=list)
    faqs: list[Faq] = Field(default_factory=list)
    other_text: str | None = Field(
        default=None, description="remaining CMS text (residences, payment plan, …)"
    )
    updated_at: datetime | None = None


class Partner(_Record):
    """A brand DarGlobal collaborates with (Aston Martin, Pagani, Trump, …)."""

    record_type: Literal["partner"] = "partner"
    name: str
    tagline: str | None = None
    description: str | None = None
    projects: list[ProjectRef] = Field(default_factory=list)


class Article(_Record):
    record_type: Literal["article"] = "article"
    kind: Literal["blog", "press", "insight"]
    title: str
    published: date | None = None
    summary: str | None = None
    body: str
    dateline: str | None = Field(default=None, description="press releases: e.g. 'DUBAI, UAE'")


class Page(_Record):
    """Any other DarGlobal page: special project templates, collections, company pages."""

    record_type: Literal["page"] = "page"
    kind: Literal["project", "project_index", "section", "company"]
    title: str
    body: str
    faqs: list[Faq] = Field(default_factory=list)


# ── Wasalt ───────────────────────────────────────────────────────────────────

Purpose = Literal["sale", "rent", "daily_rent"]


class Listing(_Record):
    """A Wasalt listing. `detail` says how much we know about it.

    - "sitemap": fields parsed from the public sitemap URL only (D-021) — no price/city
    - "page": enriched from a page Sehaj saved by hand (price, city, district, …)
    """

    record_type: Literal["listing"] = "listing"
    listing_id: str
    detail: Literal["sitemap", "page"] = "sitemap"
    purpose: Purpose
    property_type: str
    furnishing: str | None = None
    area_sqm: float | None = None
    area_inferred: bool = Field(
        default=False, description="area reconstructed from a slug that dropped its decimal point"
    )
    bedrooms: int | None = None
    bathrooms: int | None = None
    facing: str | None = None
    street_width_m: int | None = None
    url_ar: str | None = None
    listed_at: date | None = Field(default=None, description="sitemap lastmod")
    # Only from hand-saved pages:
    title: str | None = None
    price: float | None = None
    currency: str | None = None
    price_period: str | None = Field(default=None, description="rent only: yearly, monthly, …")
    city: str | None = None
    zone: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_approximate: bool | None = None
    description: str | None = None


class AreaCoverage(_Record):
    """One Wasalt search-category page: which property types are listed where."""

    record_type: Literal["area"] = "area"
    purpose: Purpose
    property_type: str
    city: str
    zone: str | None = None
    district: str | None = None


DarGlobalRecord = Annotated[Project | Partner | Article | Page, Field(discriminator="record_type")]
WasaltRecord = Annotated[Listing | AreaCoverage, Field(discriminator="record_type")]
AnyRecord = Annotated[
    Project | Partner | Article | Page | Listing | AreaCoverage,
    Field(discriminator="record_type"),
]
