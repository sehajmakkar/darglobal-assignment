"""DarGlobal parsers against trimmed real pages (tests/fixtures/darglobal/*.html)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dgbot.domain.models import Article, Page, Partner, Project
from dgbot.scraping.models import FetchMeta
from dgbot.scraping.sources.darglobal.parsers import (
    ParseError,
    brand_from_name,
    city_for,
    country_for,
    parse_page,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "darglobal"


def _meta(url: str, kind: str) -> FetchMeta:
    return FetchMeta(
        url=url,
        final_url=url,
        status=200,
        fetched_at=datetime(2026, 11, 20, tzinfo=UTC),
        body_file="x.html",
        bytes=1,
        sha256="0" * 64,
        method="browser",
        kind=kind,
    )


def _parse(fixture: str, url: str, kind: str) -> object:
    html = (FIXTURES / f"{fixture}.html").read_text(encoding="utf-8")
    return parse_page(_meta(url, kind), html)


def _no_chrome(record: object) -> None:
    assert "SHOULD NOT APPEAR" not in str(record)  # site-wide globalData never leaks in


def test_project_page() -> None:
    p = _parse("project_astera", "https://darglobal.co.uk/the-astera", "page")

    assert isinstance(p, Project)
    assert p.id == "darglobal:project:the-astera"
    assert p.name == "The Astera, Interiors by Aston Martin"
    assert p.location == "Al Marjan Island, RAK"
    assert p.city == "Al Marjan Island"
    assert p.country == "United Arab Emirates"
    assert p.brand_partner == "Aston Martin"
    assert p.latitude == pytest.approx(25.684983)
    assert p.property_type == "Beach Residences and Villas"
    assert p.description and "Al Marjan Island" in p.description
    assert "Direct Beach Access" in p.amenities
    assert any("Golden Visa" in h for h in p.highlights)
    assert len(p.faqs) >= 9 and p.faqs[0].question.startswith("What is The Astera")
    _no_chrome(p)


def test_blog_article() -> None:
    a = _parse(
        "blog", "https://darglobal.co.uk/blog/10-reasons-to-invest-in-dubai-real-estate", "blog"
    )

    assert isinstance(a, Article)
    assert a.kind == "blog"
    assert a.title.startswith("10 Reasons to Invest in Dubai")
    assert a.published is not None and a.published.isoformat() == "2025-09-23"
    assert "<" not in a.body and len(a.body) > 2000
    _no_chrome(a)


def test_press_release_has_dateline() -> None:
    url = (
        "https://darglobal.co.uk/press/"
        "dar-al-arkan-and-omran-group-announce-partnership-to-develop-aida-overlooking-the-sea-of-oman"
    )
    a = _parse("press", url, "press")

    assert isinstance(a, Article)
    assert a.kind == "press" and a.dateline == "DUBAI, UAE"
    assert "OMRAN" in a.title
    assert a.body.startswith("- Project marks DarGlobal")


def test_insight_uses_rich_text_blocks() -> None:
    a = _parse(
        "insight", "https://darglobal.co.uk/insights/149-old-park-lane-luxury-london", "insight"
    )

    assert isinstance(a, Article)
    assert a.kind == "insight"
    assert a.summary and a.summary in a.body
    _no_chrome(a)


def test_partner_page_links_its_projects() -> None:
    p = _parse("partner_aston_martin", "https://darglobal.co.uk/partners/aston-martin", "partner")

    assert isinstance(p, Partner)
    assert p.name == "Aston Martin"
    assert p.description and "Astera" in p.description
    assert any(ref.url == "https://darglobal.co.uk/the-astera" for ref in p.projects)


def test_one_of_one_page_keeps_only_its_own_property() -> None:
    # Every one-of-one page embeds the whole 8-property collection (collectionsData).
    page = _parse("oneofone_pagani", "https://darglobal.co.uk/one-of-one/project-pagani", "page")

    assert isinstance(page, Page)
    assert page.kind == "project" and page.title == "The Pagani Penthouse"
    assert page.body.startswith("The Pagani Penthouse\nDubai, UAE")
    assert "Albert Hall" not in page.body and "Fendi" not in page.body  # other properties
    _no_chrome(page)


def test_page_without_next_data_is_a_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_page(_meta("https://darglobal.co.uk/x", "page"), "<html></html>")


@pytest.mark.parametrize(
    ("location", "country", "city"),
    [
        ("Muscat, Oman - AIDA", "Oman", "Muscat"),
        ("Benahavís, Spain", "Spain", "Benahavís"),
        ("Jeddah, KSA", "Saudi Arabia", "Jeddah"),
        ("149 Old Park Lane, London, United Kingdom", "United Kingdom", "149 Old Park Lane"),
        ("Saudi Arabia", "Saudi Arabia", None),
        ("Worldwide", None, None),
    ],
)
def test_location_parsing(location: str, country: str | None, city: str | None) -> None:
    assert country_for(location) == country
    assert city_for(location) == city


@pytest.mark.parametrize(
    ("name", "brand"),
    [
        ("Da Vinci Tower interiors by Pagani", "Pagani"),
        ("Neptune Interiors by Mouawad", "Mouawad"),
        ("DG1", None),
    ],
)
def test_brand_from_name(name: str, brand: str | None) -> None:
    assert brand_from_name(name) == brand
