from datetime import UTC, datetime
from pathlib import Path

import pytest

from dgbot.scraping.sources.wasalt.parsers import (
    known_cities,
    listing_id_of,
    parse_category_url,
    parse_daily_url,
    parse_listing_page,
    parse_product_url,
    repair_area,
)

NOW = datetime(2026, 11, 20, tzinfo=UTC)
EN = "https://wasalt.sa/en/property"
FIXTURE = Path(__file__).parents[2] / "fixtures" / "wasalt" / "listing_page_5923365.html"


def test_apartment_slug() -> None:
    listing = parse_product_url(
        f"{EN}/sale/apartment-124-sqm-with-3-bedrooms-5857508", "2026-11-16", NOW
    )

    assert listing.id == "wasalt:listing:5857508"
    assert (listing.purpose, listing.property_type) == ("sale", "apartment")
    assert (listing.area_sqm, listing.area_inferred, listing.bedrooms) == (124.0, False, 3)
    assert listing.listed_at is not None and listing.listed_at.isoformat() == "2026-11-16"
    assert listing.detail == "sitemap" and listing.price is None and listing.city is None


def test_villa_slug_with_facing_and_street() -> None:
    listing = parse_product_url(
        f"{EN}/sale/villa-315-sqm-facing-north-east-on-35m-width-street-5903169", None, NOW
    )

    assert (listing.property_type, listing.area_sqm) == ("villa", 315.0)
    assert (listing.facing, listing.street_width_m) == ("north east", 35)


@pytest.mark.parametrize(
    ("slug", "kind", "furnishing"),
    [
        ("furnished-apartment-90-sqm-with-2-bedrooms", "apartment", "furnished"),
        ("semi-furnished-apartment-with-1-bedroom", "apartment", "semi-furnished"),
        ("rest-house-450-sqm-facing-north", "rest house", None),
        ("room-for-rent", "room", None),
        ("3-bedrooms-apartment-rent", "apartment", None),  # odd legacy slug
    ],
)
def test_property_type_and_furnishing(slug: str, kind: str, furnishing: str | None) -> None:
    listing = parse_product_url(f"{EN}/rent/{slug}-1", None, NOW)

    assert (listing.property_type, listing.furnishing) == (kind, furnishing)


@pytest.mark.parametrize(
    ("raw", "kind", "expected"),
    [
        (124, "apartment", (124.0, False)),
        (1077, "apartment", (107.7, True)),  # real page: "Apartment 107.7 SQM" (C-011)
        (7021, "apartment", (702.1, True)),  # real page: "Apartment 702.1 SQM"
        (17524, "floor", (175.24, True)),
        (5, "villa", (None, False)),  # nothing plausible → unknown, never a guess
        (None, "villa", (None, False)),
    ],
)
def test_repair_area(raw: int | None, kind: str, expected: tuple[float | None, bool]) -> None:
    assert repair_area(raw, kind) == expected


def test_daily_rental_slug() -> None:
    listing = parse_daily_url("https://wasalt.sa/en/dailyrental/chalet-for-booking-5577", None, NOW)

    assert listing.id == "wasalt:daily:5577"
    assert (listing.purpose, listing.property_type) == ("daily_rent", "chalet")


def test_listing_id_from_arabic_url() -> None:
    url = "https://wasalt.sa/property/sale/%D8%B4%D9%82%D8%A9-%D8%A8-3-%D8%BA%D8%B1%D9%81-5834772"
    assert listing_id_of(url) == "5834772"


def test_city_detection_and_category_split() -> None:
    locations = [
        "riyadh",
        "riyadh-al-malqa",
        "riyadh-hittin",
        "al-khobar",
        "al-khobar-al-ulaya",
        "al-khobar-ar-rakah",
        "north-riyadh",
        "north-riyadh-al-yasmin",
        "north-riyadh-al-narjis",
        "al-ula",
    ]
    cities = known_cities(locations)

    assert {"riyadh", "al-khobar", "north-riyadh", "al-ula"} <= cities
    assert "riyadh-al-malqa" not in cities

    a = parse_category_url(
        "https://wasalt.sa/en/villas-for-sale-in-al-khobar-al-ulaya", cities, NOW
    )
    assert (a.purpose, a.property_type, a.city, a.district) == (
        "sale",
        "villa",
        "Al Khobar",
        "Al Ulaya",
    )

    b = parse_category_url(
        "https://wasalt.sa/en/commercial-properties-for-rent-in-north-riyadh-al-yasmin", cities, NOW
    )
    assert (b.property_type, b.city, b.zone, b.district) == (
        "commercial property",
        "Riyadh",
        "North",
        "Al Yasmin",
    )

    c = parse_category_url("https://wasalt.sa/en/farms-for-daily-rental-in-al-ula", cities, NOW)
    assert (c.purpose, c.city, c.district) == ("daily_rent", "Al Ula", None)


def test_hand_saved_page_uses_allow_list_and_redacts_contacts() -> None:
    listing = parse_listing_page(FIXTURE.read_text(encoding="utf-8"), NOW)

    assert listing.id == "wasalt:listing:5923365" and listing.detail == "page"
    assert (listing.purpose, listing.property_type) == ("sale", "apartment")
    assert (listing.price, listing.currency) == (460000.0, "SAR")
    assert (listing.city, listing.district) == ("Jeddah", "Al Marwah")
    assert listing.area_sqm == 702.1 and listing.bedrooms == 4
    assert listing.latitude == pytest.approx(21.608, abs=1e-3)
    assert (
        listing.url
        == "https://wasalt.sa/en/property/sale/apartment-7021-sqm-with-4-bedrooms-5923365"
    )

    dumped = listing.model_dump_json()
    assert "AGENT NAME SHOULD NOT APPEAR" not in dumped  # names in CMS free text (D-019)
    assert "0551234567" not in dumped and "agent@example.com" not in dumped
    assert "9999" not in dumped  # building number: not on the allow-list
