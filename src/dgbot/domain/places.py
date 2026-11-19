"""Place names shared across layers (no I/O)."""

from __future__ import annotations

from typing import Final

# Saudi city names in Arabic, keyed by the English name used in the Wasalt data. Used for
# bilingual summaries (D-042) and for recognising Arabic city names in questions (D-044).
CITY_AR: Final[dict[str, str]] = {
    "Riyadh": "الرياض",
    "Jeddah": "جدة",
    "Makkah": "مكة المكرمة",
    "Madinah": "المدينة المنورة",
    "Dammam": "الدمام",
    "Al Khobar": "الخبر",
    "Taif": "الطائف",
    "Buraidah": "بريدة",
    "Al Ahsa": "الأحساء",
    "Unayzah": "عنيزة",
    "Abha": "أبها",
    "Khamis Mushayt": "خميس مشيط",
    "Tabuk": "تبوك",
    "Hail": "حائل",
    "Jazan": "جازان",
    "Najran": "نجران",
    "Al Kharj": "الخرج",
    "Ad Diriyah": "الدرعية",
    "Arar": "عرعر",
    "Hafar Al Batin": "حفر الباطن",
    "Al Qatif": "القطيف",
    "Dhahran": "الظهران",
    "Al Jubail": "الجبيل",
    "Yanbu": "ينبع",
    "Buqayq": "بقيق",
    "Al Khafji": "الخفجي",
    "Al Oyun": "العيون",
}
