"""Wasalt raw data → domain records (D-021).

Three inputs:
- product / daily-rental sitemap URLs → `Listing` (detail="sitemap"): the slug encodes
  purpose, type, size, bedrooms, facing and street width — but no price or city.
- category / daily-rental search URLs → `AreaCoverage`: city → district → type coverage.
- pages Sehaj saved by hand → `Listing` (detail="page"), via an **allow-list** of fields
  (D-019): agents' names appear in free-text CMS fields, so we never copy anything else.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any, Final
from urllib.parse import unquote, urlsplit

from dgbot.core.errors import DgbotError
from dgbot.domain.models import AreaCoverage, Lang, Listing, Purpose, Source
from dgbot.domain.text import clean_text, redact_contacts, title_from_slug, to_float, to_int
from dgbot.scraping.text import html_to_text

BASE: Final = "https://wasalt.sa"

# Slug prefix → (property_type, furnishing). Longest first so "furnished-apartment" wins.
_TYPE_PREFIXES: Final = (
    ("semi-furnished-apartment", "apartment", "semi-furnished"),
    ("furnished-apartment", "apartment", "furnished"),
    ("furnished-villa", "villa", "furnished"),
    ("furnished-floor", "floor", "furnished"),
    ("room-for-rent", "room", None),
    ("room-for-sale", "room", None),
    ("rest-house", "rest house", None),
    ("apartment", "apartment", None),
    ("building", "building", None),
    ("duplex", "duplex", None),
    ("chalet", "chalet", None),
    ("studio", "studio", None),
    ("villa", "villa", None),
    ("floor", "floor", None),
    ("land", "land", None),
    ("room", "room", None),
    ("farm", "farm", None),
    ("tent", "tent", None),
)
# Plausible built-up/plot area (sqm) per type, for repairing slugs that lost a decimal
# point ("apartment-7021-sqm" is really 702.1 sqm — C-011).
_AREA_BOUNDS: Final[dict[str, tuple[float, float]]] = {
    # Realistic built-up / plot sizes. Tight on purpose: in the raw slugs ~33% of
    # apartments read 10k-100k sqm (two dropped decimals) and ~20% read 500-1,000 (one).
    "apartment": (20, 400),
    "studio": (10, 150),
    "room": (5, 150),
    "floor": (40, 600),
    "duplex": (60, 800),
    "villa": (100, 1_500),
    "chalet": (30, 5_000),
    "rest house": (100, 10_000),
    "building": (100, 5_000),
    "land": (100, 5_000),
    "farm": (500, 1_000_000),
}

_PRODUCT_PATH = re.compile(r"^/(?:en/)?property/(sale|rent)/(.+)-(\d+)$")
_DAILY_PATH = re.compile(r"^/(?:en/)?dailyrental/(.+)-for-booking-(\d+)$")
_CATEGORY_PATH = re.compile(r"^/en/(.+?)-for-(sale|rent|daily-rental)-in-(.+)$")
_AREA = re.compile(r"(?:^|-)(\d+)-sqm(?:-|$)")
_BEDS = re.compile(r"(?:with-|^)(\d+)-bedrooms?(?:-|$)")
_FACING = re.compile(r"facing-(north-east|north-west|south-east|south-west|north|south|east|west)")
_STREET = re.compile(r"on-(\d+)m-width-street")
# Riyadh is split into zones; Wasalt spells the centre both "central" and "center".
_RIYADH_ZONE = re.compile(r"^(north|south|east|west|central|center)-riyadh(?:-(.+))?$")
# Same city under two slugs.
_CITY_ALIASES: Final = {"khobar": "al-khobar"}


class ParseError(DgbotError):
    """A Wasalt URL or page doesn't match the expected structure."""


# ── slug → fields ────────────────────────────────────────────────────────────


def _type_of(slug: str) -> tuple[str | None, str | None]:
    for prefix, kind, furnishing in _TYPE_PREFIXES:
        if slug == prefix or slug.startswith(prefix + "-"):
            return kind, furnishing
    # Odd legacy slugs: "3-bedrooms-apartment-rent", "sqm-land-sale"
    for prefix, kind, furnishing in _TYPE_PREFIXES:
        if f"-{prefix}-" in f"-{slug}-":
            return kind, furnishing
    return None, None


def repair_area(raw: int | None, property_type: str) -> tuple[float | None, bool]:
    """Return (area_sqm, inferred). Out-of-range sizes get a decimal point restored."""
    if raw is None:
        return None, False
    low, high = _AREA_BOUNDS.get(property_type, (1, 10_000_000))
    if low <= raw <= high:
        return float(raw), False
    for divisor in (10, 100):
        candidate = raw / divisor
        if low <= candidate <= high:
            return candidate, True
    return None, False


def parse_product_url(url: str, lastmod: str | None, scraped_at: datetime) -> Listing:
    """An English product-sitemap URL → Listing(detail="sitemap")."""
    match = _PRODUCT_PATH.match(urlsplit(url).path)
    if not match:
        raise ParseError(f"not a product URL: {url}")
    purpose, slug, listing_id = match.groups()
    return _listing_from_slug(url, slug, listing_id, purpose, lastmod, scraped_at, prefix="listing")


def parse_daily_url(url: str, lastmod: str | None, scraped_at: datetime) -> Listing:
    match = _DAILY_PATH.match(urlsplit(url).path)
    if not match:
        raise ParseError(f"not a daily-rental URL: {url}")
    slug, listing_id = match.groups()
    return _listing_from_slug(
        url, slug, listing_id, "daily_rent", lastmod, scraped_at, prefix="daily"
    )


def _listing_from_slug(
    url: str,
    slug: str,
    listing_id: str,
    purpose: str,
    lastmod: str | None,
    scraped_at: datetime,
    *,
    prefix: str,
) -> Listing:
    property_type, furnishing = _type_of(slug)
    property_type = property_type or "other"
    area_match, beds, facing, street = (
        _AREA.search(slug),
        _BEDS.search(slug),
        _FACING.search(slug),
        _STREET.search(slug),
    )
    area, inferred = repair_area(int(area_match.group(1)) if area_match else None, property_type)
    return Listing(
        id=f"wasalt:{prefix}:{listing_id}",
        source=Source.WASALT,
        url=url,
        scraped_at=scraped_at,
        listing_id=listing_id,
        purpose=_purpose(purpose),
        property_type=property_type,
        furnishing=furnishing,
        area_sqm=area,
        area_inferred=inferred,
        bedrooms=int(beds.group(1)) if beds else None,
        facing=facing.group(1).replace("-", " ") if facing else None,
        street_width_m=int(street.group(1)) if street else None,
        listed_at=_date(lastmod),
    )


def listing_id_of(url: str) -> str | None:
    """Listing id from any product URL, English or Arabic (Arabic slugs are %-encoded)."""
    match = re.search(r"-(\d+)$", unquote(urlsplit(url).path))
    return match.group(1) if match else None


def _purpose(value: str) -> Purpose:
    if value in ("sale", "rent"):
        return value  # type: ignore[return-value]
    return "daily_rent"


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


# ── category URLs → coverage ─────────────────────────────────────────────────


def known_cities(location_slugs: Iterable[str]) -> frozenset[str]:
    """City slugs = locations that prefix ≥ 2 other locations (e.g. 'riyadh-al-malqa').

    Locations under no city (small towns without district pages) count as cities too.
    """
    locations = set(location_slugs)
    candidates = {
        loc
        for loc in locations
        if sum(1 for other in locations if other.startswith(loc + "-")) >= 2
    }
    cities = {c for c in candidates if not any(c.startswith(o + "-") for o in candidates if o != c)}
    towns = {
        loc for loc in locations if not any(loc == c or loc.startswith(c + "-") for c in cities)
    }
    return frozenset(cities | towns)


def category_location(url: str) -> str | None:
    match = _CATEGORY_PATH.match(urlsplit(url).path)
    return match.group(3) if match else None


def parse_category_url(url: str, cities: frozenset[str], scraped_at: datetime) -> AreaCoverage:
    match = _CATEGORY_PATH.match(urlsplit(url).path)
    if not match:
        raise ParseError(f"not a category URL: {url}")
    type_slug, purpose_slug, location = match.groups()
    zone: str | None = None
    if zone_match := _RIYADH_ZONE.match(location):  # checked first: zones may lack a root page
        city_slug, district_slug = "riyadh", zone_match.group(2)
        zone = (
            "Central"
            if zone_match.group(1) in {"central", "center"}
            else zone_match.group(1).title()
        )
    else:
        city_slug = max(
            (c for c in cities if location == c or location.startswith(c + "-")),
            key=len,
            default=location,
        )
        district_slug = location[len(city_slug) + 1 :] or None
    city = title_from_slug(_CITY_ALIASES.get(city_slug, city_slug))
    return AreaCoverage(
        id=f"wasalt:area:{purpose_slug}:{type_slug}:{location}",
        source=Source.WASALT,
        url=url,
        scraped_at=scraped_at,
        purpose=_purpose("daily" if purpose_slug == "daily-rental" else purpose_slug),
        property_type=_singular(type_slug),
        city=city,
        zone=zone,
        district=title_from_slug(district_slug) if district_slug else None,
    )


def _singular(type_slug: str) -> str:
    """'commercial-properties' → 'commercial property', 'villas' → 'villa'."""
    words = type_slug.split("-")
    last = words[-1]
    if last.endswith("ies"):
        last = last[:-3] + "y"
    elif last.endswith("s"):
        last = last[:-1]
    return " ".join([*words[:-1], last])


# ── hand-saved listing pages ─────────────────────────────────────────────────

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
# Allow-list (D-019). Land listings report size as `carpetArea` ("Land Area").
_ATTRIBUTE_KEYS: Final = frozenset(
    {"noOfBedrooms", "noOfBathrooms", "builtUpArea", "carpetArea", "plotArea"}
)
_RENT_PERIODS: Final = {"/year": "yearly", "/month": "monthly", "/week": "weekly", "/day": "daily"}


def parse_listing_page(html: str, scraped_at: datetime) -> Listing:
    """A listing page saved by hand → Listing(detail="page"). Allow-list only (D-019)."""
    match = _NEXT_DATA.search(html)
    if not match:
        raise ParseError("no __NEXT_DATA__ in saved page")
    data = json.loads(match.group(1))
    props: dict[str, Any] = data["props"]["pageProps"]
    details: dict[str, Any] = props["propertyDetailsV3"]
    info: dict[str, Any] = details.get("propertyInfo") or {}
    params: dict[str, Any] = props.get("params") or {}
    lang = Lang.AR if data.get("locale") == "ar" else Lang.EN

    listing_id = str(details["id"])
    purpose = _purpose(str(params.get("slug") or info.get("propertyFor") or "").lower())
    path = f"property/{params.get('slug')}/{params.get('slug-id')}"
    url = f"{BASE}/{path}" if lang is Lang.AR else f"{BASE}/en/{path}"

    attrs = {
        a.get("key"): a.get("value")
        for a in details.get("attributes") or []
        if isinstance(a, dict) and a.get("key") in _ATTRIBUTE_KEYS
    }
    subtype = str(info.get("propertySubTypeSlug") or "other")
    property_type = _type_of(subtype)[0] or subtype.replace("-", " ")  # "villa-townhouse" → villa
    sale, rent = to_float(info.get("salePrice")), to_float(info.get("expectedRent"))
    location = details.get("location") or {}

    return Listing(
        id=f"wasalt:listing:{listing_id}" + (":ar" if lang is Lang.AR else ""),
        source=Source.WASALT,
        url=url,
        lang=lang,
        scraped_at=scraped_at,
        listing_id=listing_id,
        detail="page",
        purpose=purpose,
        property_type=property_type,
        furnishing=_clean_enum(info.get("furnishingType")),
        area_sqm=to_float(
            attrs.get("builtUpArea") or attrs.get("carpetArea") or attrs.get("plotArea")
        ),
        bedrooms=to_int(attrs.get("noOfBedrooms")),
        bathrooms=to_int(attrs.get("noOfBathrooms")),
        facing=_clean_enum(info.get("facingType")),
        street_width_m=_street_width(details.get("additionalAttributes")),
        title=clean_text(info.get("title")),
        price=sale if purpose == "sale" else (rent or sale),
        currency=clean_text(info.get("currencyType")),
        price_period=_rent_period(info) if purpose != "sale" else None,
        city=clean_text(info.get("city")),
        zone=_zone(info),
        district=clean_text(info.get("district")),
        latitude=to_float(location.get("lat")),
        longitude=to_float(location.get("lon")),
        location_approximate=details.get("isApproxLocation")
        if isinstance(details.get("isApproxLocation"), bool)
        else None,
        description=_redact_names(
            redact_contacts(html_to_text(info.get("description"))), _contact_names(details)
        ),
        listed_at=_date(details.get("publishedAt") or details.get("updatedAt")),
    )


_CONTACT_EN = re.compile(r"To contact (.+?), please", re.S)
_CONTACT_AR = re.compile(r"للتواصل مع (.+?)[,،]", re.S)


def _contact_names(details: dict[str, Any]) -> set[str]:
    """The agent/owner names this page itself reveals (contact prompts, owner block).

    We never store them; we use them to scrub the free-text description (D-019).
    """
    names: set[str] = set()
    lead = details.get("leadContactInfo") or {}
    for pattern, key in ((_CONTACT_EN, "enMessageBody"), (_CONTACT_AR, "arMessageBody")):
        if isinstance(lead.get(key), str) and (m := pattern.search(lead[key])):
            names.add(m.group(1).strip())
    owner = details.get("propertyOwner") or {}
    for key in ("name", "managedBy", "fullName", "agentName"):
        if isinstance(owner.get(key), str) and len(owner[key].strip()) > 2:
            names.add(owner[key].strip())
    return names


def _redact_names(text: str | None, names: set[str]) -> str | None:
    if not text:
        return text
    for name in sorted(names, key=len, reverse=True):
        text = text.replace(name, "[name removed]")
    return text


def _zone(info: dict[str, Any]) -> str | None:
    """Wasalt often repeats the district in `zone`; keep it only when it adds something."""
    zone, district = clean_text(info.get("zone")), clean_text(info.get("district"))
    return None if zone is None or (district and zone.casefold() == district.casefold()) else zone


def _rent_period(info: dict[str, Any]) -> str | None:
    """`rentFreq` = {"yearly": {"default_freq": true, ...}}; else "/Year"-style text."""
    freq = info.get("rentFreq")
    if isinstance(freq, dict) and freq:
        default = next(
            (k for k, v in freq.items() if isinstance(v, dict) and v.get("default_freq")), None
        )
        return str(default or next(iter(freq)))
    text = str(info.get("expectedRentType") or "").strip().lower()
    return _RENT_PERIODS.get(text)


def _street_width(additional: Any) -> int | None:
    """'10 m' from additionalAttributes[key=propertyStreetWidth] (the only one we keep)."""
    for item in additional or []:
        if isinstance(item, dict) and item.get("key") == "propertyStreetWidth":
            match = re.search(r"\d+", str(item.get("value") or ""))
            return int(match.group(0)) if match else None
    return None


def _clean_enum(value: Any) -> str | None:
    text = clean_text(value) if isinstance(value, str) else None
    return None if text is None or text.lower() in {"none", "null", "n/a"} else text.lower()
