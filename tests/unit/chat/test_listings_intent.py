import pytest

from dgbot.chat.listings_intent import ListingQuery, parse_listing_query

CITIES = {
    "Riyadh": "Riyadh",
    "Jeddah": "Jeddah",
    "Al Khobar": "Al Khobar",
    "Khobar": "Al Khobar",
    "الرياض": "Riyadh",
    "جدة": "Jeddah",
    "الخبر": "Al Khobar",
}


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("3-bed villas for rent in Riyadh", ListingQuery("rent", "villa", 3, "Riyadh")),
        ("Apartments for sale in Jeddah", ListingQuery("sale", "apartment", None, "Jeddah")),
        ("land plots for sale in Khobar", ListingQuery("sale", "land", None, "Al Khobar")),
        (
            "How many chalets for daily rental does Wasalt have?",
            ListingQuery("daily_rent", "chalet", None, None),
        ),
        ("فلل للبيع في جدة", ListingQuery("sale", "villa", None, "Jeddah")),
        ("شقة بغرفتين للايجار في الرياض", ListingQuery("rent", "apartment", 2, "Riyadh")),
        ("شقة ٣ غرف للبيع في الخبر", ListingQuery("sale", "apartment", 3, "Al Khobar")),
    ],
)
def test_parses_listing_questions(question: str, expected: ListingQuery) -> None:
    assert parse_listing_query(question, CITIES) == expected


@pytest.mark.parametrize(
    "question",
    [
        "Tell me about Trump Tower Jeddah",  # no type/purpose
        "DarGlobal villas in Jeddah",  # DarGlobal question
        "ما هي مشاريع دار جلوبال في جدة؟",  # DarGlobal, Arabic
        "What is The Astera?",
        "villas for sale",  # no city and no Wasalt mention
    ],
)
def test_ignores_non_listing_questions(question: str) -> None:
    assert parse_listing_query(question, CITIES) is None
