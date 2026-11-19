"""Exact lookups over `listings.sqlite` (D-040) for parsed listing questions (D-044).

Honest about the data: sitemap listings have no city, so counts are nationwide by
purpose/type/bedrooms; the city part comes from the area-coverage table (which districts
have such listings) and from the few hand-saved listings that do have a city and price.
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass
from pathlib import Path

from dgbot.chat.listings_intent import ListingQuery

_PURPOSE_TEXT = {"sale": "for sale", "rent": "for rent", "daily_rent": "for daily rental"}


def _plural(kind: str | None) -> str:
    return "properties" if kind is None else kind if kind.endswith("s") else kind + "s"


@dataclass(frozen=True)
class ListingLookup:
    title: str
    url: str
    text: str


class ListingsDB:
    def __init__(self, path: Path) -> None:
        # Read-only; shared across request threads (no writes after build).
        self._db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)

    def close(self) -> None:
        self._db.close()

    def cities(self) -> list[str]:
        return [row[0] for row in self._db.execute("SELECT DISTINCT city FROM areas ORDER BY city")]

    def lookup(self, query: ListingQuery) -> ListingLookup:
        where: list[str] = ["lang = 'en'"]
        args: list[str | int] = []
        if query.purpose:
            where.append("purpose = ?")
            args.append(query.purpose)
        if query.property_type:
            where.append("property_type = ?")
            args.append(query.property_type)
        if query.bedrooms:
            where.append("bedrooms = ?")
            args.append(query.bedrooms)
        clause = " AND ".join(where)
        count = self._db.execute(f"SELECT COUNT(*) FROM listings WHERE {clause}", args).fetchone()[
            0
        ]
        sizes = [
            float(r[0])
            for r in self._db.execute(
                f"SELECT area_sqm FROM listings WHERE {clause} AND area_sqm IS NOT NULL",
                args,
            )
        ]
        lines = [
            f"Wasalt listing database — {query.describe()} (exact counts for this dataset)",
            f"Matching listings across Saudi Arabia: {count:,}"
            + (
                " (listing URLs carry no city, so this count is nationwide, not per city; "
                "بالعربية: العدد على مستوى المملكة كلها وليس للمدينة المذكورة)."
                if query.city
                else "."
            ),
        ]
        if len(sizes) >= 5:
            lines.append(
                f"Typical size: median {statistics.median(sizes):,.0f} sqm "
                "(sizes from listing URLs, some approximate)."
            )
        if not query.bedrooms and query.property_type in {"apartment", "villa", "floor"}:
            mix = self._db.execute(
                f"SELECT bedrooms, COUNT(*) FROM listings WHERE {clause} AND bedrooms IS NOT NULL "
                "GROUP BY bedrooms ORDER BY COUNT(*) DESC LIMIT 4",
                args,
            ).fetchall()
            if mix:
                lines.append(
                    "Most common bedroom counts: "
                    + ", ".join(f"{b} bedrooms ({n:,})" for b, n in mix)
                    + "."
                )
        url = "https://wasalt.sa/en"
        if query.city:
            url, coverage = self._coverage(query)
            lines.append(coverage)
        lines += self._priced_examples(query)
        return ListingLookup(
            title=f"Wasalt listing database: {query.describe()}", url=url, text="\n".join(lines)
        )

    def _coverage(self, query: ListingQuery) -> tuple[str, str]:
        where: list[str] = ["city = ?"]
        args: list[str | int] = [query.city or ""]
        if query.purpose:
            where.append("purpose = ?")
            args.append(query.purpose)
        if query.property_type:
            where.append("property_type IN (?, 'property')")
            args.append(query.property_type)
        rows = self._db.execute(
            f"SELECT district, url, property_type FROM areas WHERE {' AND '.join(where)}",
            args,
        ).fetchall()
        districts = sorted({d for d, _, _ in rows if d})
        root = next(
            (u for d, u, t in rows if d is None and t == query.property_type), None
        ) or next((u for d, u, _ in rows if d is None), "https://wasalt.sa/en")
        if not rows:
            return root, f"Wasalt has no category pages for {query.describe()} in this dataset."
        sample = ", ".join(districts[:25])
        return root, (
            f"In {query.city}, Wasalt lists {_plural(query.property_type)} "
            f"{_PURPOSE_TEXT.get(query.purpose or '', '')} in {len(districts)} districts"
            + (f", including {sample}." if sample else ".")
        )

    def _priced_examples(self, query: ListingQuery) -> list[str]:
        where: list[str] = ["price IS NOT NULL", "lang = 'en'"]
        args: list[str | int] = []
        for column, value in (
            ("purpose", query.purpose),
            ("property_type", query.property_type),
            ("city", query.city),
        ):
            if value:
                where.append(f"{column} = ?")
                args.append(value)
        rows = self._db.execute(
            "SELECT title, price, currency, price_period, district, city, url FROM listings "
            f"WHERE {' AND '.join(where)} ORDER BY price LIMIT 3",
            args,
        ).fetchall()
        if not rows:
            return [
                "No priced example matches this search "
                "(prices exist only for a small hand-saved sample)."
            ]
        out = ["Priced examples (from listing pages saved by hand):"]
        for title, price, currency, period, district, city, url in rows:
            per = f" per {period.removesuffix('ly')}" if period else ""
            out.append(
                f"- {title}: {float(price):,.0f} {currency}{per}, {district}, {city} ({url})"
            )
        return out
