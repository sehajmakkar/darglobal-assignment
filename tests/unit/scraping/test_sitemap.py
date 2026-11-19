import gzip

import pytest
from defusedxml import DefusedXmlException

from dgbot.scraping.sitemap import dedupe, normalize_url, parse_sitemap

URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc> https://darglobal.co.uk/the-astera </loc><lastmod>2026-11-19</lastmod></url>
  <url><loc>https://darglobal.co.uk/about</loc></url>
  <url><lastmod>2026-11-19</lastmod></url>
</urlset>"""

INDEX = b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://cdn.example.com/a.xml.gz</loc></sitemap>
</sitemapindex>"""


def test_parses_urlset_and_skips_entries_without_loc() -> None:
    kind, entries = parse_sitemap(URLSET)

    assert kind == "urlset"
    assert [e.url for e in entries] == [
        "https://darglobal.co.uk/the-astera",
        "https://darglobal.co.uk/about",
    ]
    assert entries[0].lastmod == "2026-11-19"
    assert entries[1].lastmod is None


def test_parses_gzipped_sitemap_index() -> None:
    kind, entries = parse_sitemap(gzip.compress(INDEX))

    assert kind == "sitemapindex"
    assert entries[0].url == "https://cdn.example.com/a.xml.gz"


def test_rejects_non_sitemap_xml() -> None:
    with pytest.raises(ValueError, match="not a sitemap"):
        parse_sitemap(b"<html><body/></html>")


def test_rejects_entity_expansion_attacks() -> None:
    bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>
<urlset><url><loc>&lol2;</loc></url></urlset>"""
    with pytest.raises(DefusedXmlException):
        parse_sitemap(bomb)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  http://DarGlobal.co.uk/La-Collina/ ", "https://darglobal.co.uk/La-Collina"),
        ("https://darglobal.co.uk/", "https://darglobal.co.uk/"),
        ("https://darglobal.co.uk/x?utm_source=a&b=2&a=1#top", "https://darglobal.co.uk/x?a=1&b=2"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_normalize_url_can_force_host() -> None:
    assert normalize_url("https://www.darglobal.co.uk/faq", force_host="darglobal.co.uk") == (
        "https://darglobal.co.uk/faq"
    )


def test_dedupe_is_case_insensitive_and_keeps_first_spelling() -> None:
    urls = ["https://x.com/La-Collina", "https://x.com/la-collina", "https://x.com/a"]

    assert dedupe(urls) == ["https://x.com/La-Collina", "https://x.com/a"]
