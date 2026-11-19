"""Pure text/number normalisation shared by the parsers. No I/O, no third-party deps."""

from __future__ import annotations

import re
import unicodedata

# Arabic-Indic (U+0660-0669) and Extended/Persian (U+06F0-06F9) digits → ASCII.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_INLINE_SPACE = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")

# Contact details inside free text (D-019): phones (Saudi/international), emails, links.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_URL = re.compile(r"(https?://|www\.)\S+", re.I)
_PHONE = re.compile(r"(?<!\w)(\+?\d[\d\s\-().]{7,}\d)(?!\w)")


def ascii_digits(text: str) -> str:
    return text.translate(_DIGITS)


def clean_text(text: str | None) -> str | None:
    """NFKC, ASCII digits, collapse spaces (keeping paragraph breaks), trim. Empty → None."""
    if text is None:
        return None
    text = unicodedata.normalize("NFKC", ascii_digits(text)).replace("\r", "")
    lines = [_INLINE_SPACE.sub(" ", line).strip() for line in text.split("\n")]
    out = _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
    return out or None


def redact_contacts(text: str | None) -> str | None:
    """Remove phone numbers, emails and links from user-written text (D-019)."""
    if text is None:
        return None
    text = _EMAIL.sub("[email removed]", text)
    text = _URL.sub("[link removed]", text)
    return _PHONE.sub(_phone_or_keep, text)


def _phone_or_keep(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    # 9+ digits looks like a phone; shorter runs are prices, areas, years.
    return "[phone removed]" if len(digits) >= 9 else match.group(0)


def to_float(value: object) -> float | None:
    """'1,250,000' / '١٢٥٠' / 460000 / '' → float or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = ascii_digits(str(value)).replace(",", "").strip()
    try:
        return float(text) if text else None
    except ValueError:
        return None


def to_int(value: object) -> int | None:
    number = to_float(value)
    return int(number) if number is not None and number.is_integer() else None


def title_from_slug(slug: str) -> str:
    """'al-khobar' → 'Al Khobar'."""
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def dedupe_lines(lines: list[str]) -> list[str]:
    """Drop repeated lines (CMS templates repeat headings), keep first occurrence order."""
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.casefold()
        if line and key not in seen:
            seen.add(key)
            out.append(line)
    return out
