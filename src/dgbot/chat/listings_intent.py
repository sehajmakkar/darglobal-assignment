"""Deterministic EN/AR intent parsing for structured Wasalt questions (D-044).

"3-bed villas for rent in Riyadh" / "فلل للبيع في جدة" → ListingQuery. No LLM call: with
50 free requests a day, every question gets exactly one LLM call, and free models' tool
calling is unreliable anyway. The parsed query drives an exact SQLite lookup whose result
is added to the prompt as one more numbered source.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from dgbot.domain.models import Purpose
from dgbot.domain.text import ascii_digits

# (pattern, value). Longest / most specific first.
_TYPES: Final = (
    (r"rest[\s-]?houses?|istirahas?|استراحات?|استراحة", "rest house"),
    (r"apartments?|flats?|شقق|شقة|شقه", "apartment"),
    (r"villas?|townhouses?|فلل|فيلا|فيلل|فيلات", "villa"),
    (r"lands?|plots?|أراضي|اراضي|أرض|ارض", "land"),
    (r"floors?|أدوار|ادوار|دور", "floor"),
    (r"buildings?|عمارات|عمارة", "building"),
    (r"chalets?|شاليهات|شاليه", "chalet"),
    (r"studios?|استوديو|ستوديو", "studio"),
    (r"duplex(?:es)?|دوبلكس", "duplex"),
    (r"farms?|مزارع|مزرعة", "farm"),
    (r"rooms? for (?:rent|sale)", "room"),
)
_PURPOSES: Final = (
    (
        r"daily|per night|nightly|short[\s-]?stay|holiday rental|booking|يومي|يومية|حجز",
        "daily_rent",
    ),
    (r"for rent|to rent|rent(?:al|ing)?|lease|to let|للإيجار|للايجار|إيجار|ايجار|أجار", "rent"),
    (r"for sale|buy(?:ing)?|purchase|sale|selling|للبيع|بيع|شراء|تمليك", "sale"),
)
_BEDROOMS_EN: Final = re.compile(r"\b(\d{1,2})\s*[- ]?\s*(?:bed(?:room)?s?|br|bhk)\b", re.I)
_BEDROOMS_AR: Final = re.compile(r"(\d{1,2})\s*(?:غرف|غرفة)")
_TWO_BEDROOMS_AR: Final = re.compile(r"غرفتين|غرفتان")
_WASALT: Final = re.compile(r"wasalt|وصلت|وصلة", re.I)
_DARGLOBAL: Final = re.compile(r"dar\s?global|دار\s?جلوبال|darglobal", re.I)


@dataclass(frozen=True)
class ListingQuery:
    purpose: Purpose | None
    property_type: str | None
    bedrooms: int | None
    city: str | None

    def describe(self) -> str:
        bits = [
            f"{self.bedrooms}-bedroom" if self.bedrooms else None,
            self.property_type or "properties",
        ]
        purpose = {"sale": "for sale", "rent": "for rent", "daily_rent": "for daily rental"}
        text = " ".join(b for b in bits if b)
        if self.purpose:
            text += f" {purpose[self.purpose]}"
        if self.city:
            text += f" in {self.city}"
        return text


def _first(patterns: Iterable[tuple[str, str]], text: str) -> str | None:
    for pattern, value in patterns:
        if re.search(rf"(?<!\w)(?:{pattern})(?!\w)", text, re.I):
            return value
    return None


def parse_listing_query(question: str, cities: dict[str, str]) -> ListingQuery | None:
    """`cities` maps every recognised spelling (English, Arabic) → canonical city name."""
    text = ascii_digits(question)
    if _DARGLOBAL.search(text):
        return None  # DarGlobal questions are answered from DarGlobal sources only
    property_type = _first(_TYPES, text)
    purpose = _first(_PURPOSES, text)
    city = _find_city(text, cities)
    mentions_wasalt = bool(_WASALT.search(text))
    if not (property_type or purpose) or not (city or mentions_wasalt):
        return None
    bedrooms = None
    if match := _BEDROOMS_EN.search(text) or _BEDROOMS_AR.search(text):
        bedrooms = int(match.group(1))
    elif _TWO_BEDROOMS_AR.search(text):
        bedrooms = 2
    return ListingQuery(purpose, property_type, bedrooms, city)  # type: ignore[arg-type]


def _find_city(text: str, cities: dict[str, str]) -> str | None:
    lowered = text.casefold()
    for spelling in sorted(cities, key=len, reverse=True):  # "Al Khobar" before "Khobar"
        needle = spelling.casefold()
        if re.search(rf"(?<!\w)(?:ال)?{re.escape(needle)}(?!\w)", lowered):
            return cities[spelling]
    return None
