import pytest

from dgbot.domain.text import (
    ascii_digits,
    clean_text,
    dedupe_lines,
    redact_contacts,
    title_from_slug,
    to_float,
    to_int,
)


def test_arabic_digits_become_ascii() -> None:
    assert ascii_digits("السعر ١٢٥٠٠٠ ريال، ۳ غرف") == "السعر 125000 ريال، 3 غرف"


def test_clean_text_collapses_spaces_but_keeps_paragraphs() -> None:
    raw = "  Hello\u00a0  world \r\n\n\n\n  Second   para  "
    assert clean_text(raw) == "Hello world\n\nSecond para"


@pytest.mark.parametrize("raw", [None, "", "   \n  "])
def test_clean_text_empty_is_none(raw: str | None) -> None:
    assert clean_text(raw) is None


def test_redacts_phones_emails_links_but_keeps_prices_and_areas() -> None:
    text = (
        "Call 0551234567 or +966 55 123 4567, email agent@example.com, "
        "see https://x.co/a. Price 460,000 SAR, 702.1 sqm, built 2019."
    )
    out = redact_contacts(text)
    assert out is not None
    assert "0551234567" not in out and "123 4567" not in out
    assert "agent@example.com" not in out and "https://x.co" not in out
    assert "460,000 SAR" in out and "702.1 sqm" in out and "2019" in out


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1,250,000", 1_250_000.0), ("١٢٥٠", 1250.0), (460000, 460000.0), ("", None), ("n/a", None)],
)
def test_to_float(value: object, expected: float | None) -> None:
    assert to_float(value) == expected


def test_to_int_rejects_fractions_and_bools() -> None:
    assert to_int("3") == 3
    assert to_int("2.5") is None
    assert to_int(True) is None


def test_title_from_slug() -> None:
    assert title_from_slug("al-khobar") == "Al Khobar"


def test_dedupe_lines_is_case_insensitive() -> None:
    assert dedupe_lines(["Amenities", "Pool", "AMENITIES", "", "Gym"]) == [
        "Amenities",
        "Pool",
        "Gym",
    ]
