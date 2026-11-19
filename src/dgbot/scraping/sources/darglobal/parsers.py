"""DarGlobal raw page → domain record. Pure functions over stored HTML (D-024).

Every page is server-rendered Next.js with the Strapi CMS payload in `__NEXT_DATA__`.
Order of preference: structured CMS fields → JSON-LD → generic CMS text (`cms_text`).
Site-wide `globalData` (menus, footer) is never read, so it can't flood the index.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Final, Literal
from urllib.parse import urlsplit

from dgbot.core.errors import DgbotError
from dgbot.domain.models import (
    Article,
    DarGlobalRecord,
    Fact,
    Faq,
    Page,
    Partner,
    Project,
    ProjectRef,
    Source,
)
from dgbot.domain.text import clean_text, dedupe_lines, to_float
from dgbot.scraping.models import FetchMeta
from dgbot.scraping.text import blocks_to_text, cms_text, html_to_text

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_JSON_LD = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
# Keys in pageProps that are page chrome, not content.
_CHROME_KEYS: Final = frozenset(
    {"globalData", "locale", "isMobile", "slug", "pageLayoutStyle", "inventoryDataLength", "params"}
)
_PROJECT_ROUTES: Final = (
    "/one-of-one/[slug]",
    "/rayana/[slug]",
    "/amaya/[slug]",
    "/trump-plaza/[slug]",
)

# Location text → country (order matters: most specific first).
_COUNTRY_KEYWORDS: Final = (
    (
        "United Arab Emirates",
        ("dubai", "uae", "united arab emirates", "ras al khaimah", "rak", "abu dhabi", "al marjan"),
    ),
    ("Saudi Arabia", ("saudi", "ksa", "riyadh", "jeddah", "makkah", "madinah", "khobar", "dammam")),
    ("Oman", ("oman", "muscat", "aida", "sohar")),
    ("Qatar", ("qatar", "doha", "simaisma", "qetaifan")),
    ("United Kingdom", ("london", "united kingdom", "uk", "england", "mayfair")),
    ("Spain", ("spain", "marbella", "benahav", "cortesin", "estepona", "casares")),
    ("Maldives", ("maldives",)),
    ("Bosnia and Herzegovina", ("bosnia", "sarajevo")),
)
_NOT_CITIES: Final = frozenset(
    {c.lower() for c, _ in _COUNTRY_KEYWORDS}
    | {"uae", "ksa", "uk", "saudi", "oman", "qatar", "spain", "maldives", "worldwide"}
)
_BRAND_IN_NAME = re.compile(
    r"\b(?:interiors|design(?:ed)?(?: inspired)?|residences|villas)?\s*by\s+(.+)$", re.I
)


class ParseError(DgbotError):
    """A stored page doesn't have the structure its parser expects."""


# ── helpers ──────────────────────────────────────────────────────────────────


def next_data(html: str) -> dict[str, Any]:
    match = _NEXT_DATA.search(html)
    if not match:
        raise ParseError("no __NEXT_DATA__ script in page")
    data: dict[str, Any] = json.loads(match.group(1))
    return data


def json_ld_nodes(html: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for block in _JSON_LD.findall(html):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = parsed.get("@graph", [parsed]) if isinstance(parsed, dict) else parsed
        nodes.extend(item for item in items if isinstance(item, dict))
    return nodes


def _unwrap(node: Any) -> dict[str, Any]:
    """Strapi shapes: {data: [...]}, [...], {id, attributes: {...}} → the attributes dict."""
    for _ in range(4):
        if isinstance(node, dict) and "data" in node and len(node) <= 2:
            node = node["data"]
        elif isinstance(node, list):
            node = node[0] if node else {}
        elif isinstance(node, dict) and isinstance(node.get("attributes"), dict):
            node = node["attributes"]
        else:
            break
    return node if isinstance(node, dict) else {}


def _get(node: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _str(value: Any) -> str | None:
    return clean_text(value) if isinstance(value, str) else None


def _rich(value: Any) -> str | None:
    """A CMS text field that may be plain, HTML, or Strapi blocks."""
    if isinstance(value, list):
        return blocks_to_text(value)
    if isinstance(value, str):
        return html_to_text(value)
    return None


def _date(value: Any) -> date | None:
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _slug(url: str) -> str:
    return urlsplit(url).path.strip("/").lower() or "home"


def _record_id(kind: str, url: str) -> str:
    return f"darglobal:{kind}:{_slug(url)}"


def country_for(location: str | None) -> str | None:
    if not location:
        return None
    text = f" {location.lower()} "
    for country, keywords in _COUNTRY_KEYWORDS:
        if any(re.search(rf"\b{re.escape(k)}\b", text) for k in keywords):
            return country
    return None


def city_for(location: str | None) -> str | None:
    """First part of 'Muscat, Oman - AIDA' → 'Muscat'; None when it's just a country."""
    if not location:
        return None
    first = location.split(",")[0].split(" - ")[0].strip()
    if not first or first.lower() in _NOT_CITIES:
        return None
    return first


def _types(node: dict[str, Any]) -> set[str]:
    """JSON-LD `@type` may be a string or a list of strings."""
    value = node.get("@type")
    if isinstance(value, str):
        return {value}
    return {v for v in value if isinstance(v, str)} if isinstance(value, list) else set()


def brand_from_name(name: str) -> str | None:
    """'Da Vinci Tower, Interiors By Pagani' → 'Pagani'."""
    match = _BRAND_IN_NAME.search(name)
    return clean_text(match.group(1)) if match else None


def _faqs_from_cms(faq_content: Any) -> list[Faq]:
    out: list[Faq] = []
    for section in faq_content or []:
        for item in _get(section, "faqs") or []:
            question, answer = _str(item.get("question")), _rich(item.get("answer"))
            if question and answer:
                out.append(Faq(question=question, answer=answer))
    return out


def faqs_from_json_ld(html: str) -> list[Faq]:
    out: list[Faq] = []
    for node in json_ld_nodes(html):
        if "FAQPage" not in _types(node):
            continue
        for q in node.get("mainEntity") or []:
            question = _str(q.get("name"))
            answer = _rich(_get(q, "acceptedAnswer", "text"))
            if question and answer:
                out.append(Faq(question=question, answer=answer))
    return out


# ── parsers per page type ────────────────────────────────────────────────────


def parse_project(meta: FetchMeta, html: str, data: dict[str, Any]) -> Project:
    attrs = _unwrap(data["projectDetailsData"])
    details = attrs.get("ProjectDetails") or {}
    banner = details.get("ProjectBanner") or {}
    about = details.get("AboutProject") or {}
    place = details.get("loaction") or details.get("location") or {}  # sic: CMS typo
    geo = place.get("locationDetailsWithImages") or {}

    name = _str(attrs.get("title")) or _str(banner.get("Heading"))
    if not name:
        raise ParseError(f"project without a title: {meta.url}")
    location = _str(banner.get("Location")) or _str(geo.get("location"))

    facts = [
        Fact(name=n, value=v)
        for item in about.get("AboutDetailsType") or []
        if (n := _str(item.get("name"))) and (v := _str(item.get("value")))
    ]

    def fact(*names: str) -> str | None:
        wanted = {n.casefold() for n in names}
        return next((f.value for f in facts if f.name.casefold().strip() in wanted), None)

    amenities = dedupe_lines(
        [
            n
            for section in ("Amenities", "newAmenities")
            for item in _get(details, section, "amenitiesList")
            or _get(attrs, section, "amenitiesList")
            or []
            if (n := _str(item.get("name")))
        ]
    )
    highlights = dedupe_lines(
        [
            line
            for item in (_get(details, "KeyFeatures", "keyfeaturelist") or [])
            + (_get(details, "whyInvest", "investlist") or [])
            if (line := _join(_str(item.get("name")), _str(item.get("value"))))
        ]
    )
    nearby = [
        line
        for item in place.get("nearByLandmark") or []
        if (
            line := _join(
                _str(item.get("name") or item.get("title")),
                _str(item.get("value") or item.get("distance")),
            )
        )
    ]
    other = cms_text(
        {
            k: details.get(k)
            for k in ("chooseYourResidence", "PaymentMode", "ProgressUpdate", "PhotoGallery")
            if details.get(k)
        }
    )
    faqs = _faqs_from_cms(attrs.get("faqContent")) or faqs_from_json_ld(html)

    return Project(
        id=_record_id("project", meta.url),
        source=Source.DARGLOBAL,
        url=meta.url,
        scraped_at=meta.fetched_at,
        name=name,
        location=location,
        city=city_for(location),
        country=country_for(" ".join(filter(None, [location, name]))),
        latitude=to_float(geo.get("lat")),
        longitude=to_float(geo.get("long")),
        brand_partner=brand_from_name(name),
        property_type=fact("Property Type", "Project Type"),
        status=fact("Status", "Stage"),
        unit_types=fact("Unit Type", "Unit type"),
        facts=facts,
        description=_rich(about.get("richDescription")) or _rich(about.get("description")),
        location_description=_rich(place.get("description")),
        amenities=amenities,
        highlights=highlights,
        nearby=nearby,
        faqs=faqs,
        other_text=other,
        updated_at=_datetime(attrs.get("updatedAt")),
    )


def _join(name: str | None, value: str | None) -> str | None:
    if name and value and value.casefold() not in name.casefold():
        return f"{name.rstrip(':')}: {value}"
    return name or value


def parse_blog(meta: FetchMeta, data: dict[str, Any]) -> Article:
    attrs = _unwrap(data.get("blogDetails"))
    body = html_to_text(data.get("blogDetailsHTML")) or _rich(attrs.get("content"))
    return _article(
        meta, "blog", attrs.get("heading"), attrs.get("date"), attrs.get("description"), body
    )


def parse_press(meta: FetchMeta, data: dict[str, Any]) -> Article:
    attrs = _unwrap(data.get("pressDetails"))
    body = html_to_text(data.get("pressDetailsHTML")) or _rich(attrs.get("description"))
    article = _article(
        meta, "press", attrs.get("heading"), attrs.get("date"), attrs.get("cardDescription"), body
    )
    return article.model_copy(update={"dateline": _str(attrs.get("location"))})


def parse_insight(meta: FetchMeta, data: dict[str, Any]) -> Article:
    attrs = _unwrap(data.get("pageData"))
    summary = _rich(attrs.get("summary"))
    answer = _rich(attrs.get("answer"))
    body = "\n\n".join(p for p in (summary, answer) if p)
    return _article(meta, "insight", attrs.get("title"), attrs.get("published"), summary, body)


def _article(
    meta: FetchMeta,
    kind: Literal["blog", "press", "insight"],
    title: Any,
    published: Any,
    summary: Any,
    body: str | None,
) -> Article:
    title_text = _str(title)
    if not title_text or not body:
        raise ParseError(f"{kind} without title/body: {meta.url}")
    return Article(
        id=_record_id(kind, meta.url),
        source=Source.DARGLOBAL,
        url=meta.url,
        scraped_at=meta.fetched_at,
        kind=kind,
        title=title_text,
        published=_date(published),
        summary=_rich(summary),
        body=body,
    )


def parse_partner(meta: FetchMeta, data: dict[str, Any]) -> Partner:
    attrs = _unwrap(data.get("collabData"))
    overview = attrs.get("overview") or {}
    hero = attrs.get("heroBanner") or {}
    tagline = _str(hero.get("subheading")) or _str(overview.get("subHeading"))
    # Taglines read "<Brand> Real Estate & Branded Luxury Residences" — the cleanest name.
    name = tagline.split(" Real Estate")[0].strip() if tagline and " Real Estate" in tagline else ""
    if not name:
        name = _slug(meta.url).split("/")[-1].replace("-", " ")
    name = name.title() if name.isupper() or name.islower() else name
    projects = [
        ProjectRef(
            name=title,
            url=f"https://darglobal.co.uk{link}"
            if isinstance(link := item.get("Link"), str) and link.startswith("/")
            else None,
            location=_str(item.get("location")),
        )
        for item in attrs.get("relatedProjects") or []
        if (title := _str(item.get("title")))
    ]
    return Partner(
        id=_record_id("partner", meta.url),
        source=Source.DARGLOBAL,
        url=meta.url,
        scraped_at=meta.fetched_at,
        name=name,
        tagline=tagline,
        description=_rich(overview.get("description")),
        projects=projects,
    )


def parse_generic(meta: FetchMeta, html: str, data: dict[str, Any], route: str) -> Page | None:
    """Any other template: title + all CMS text + FAQs from JSON-LD."""
    props = data["props"]["pageProps"]
    content = {k: v for k, v in props.items() if k not in _CHROME_KEYS}
    body = cms_text(content)
    if not body:
        return None
    ld = json_ld_nodes(html)
    is_listing = any(_types(n) & {"RealEstateListing", "Residence", "Place"} for n in ld)
    kind: Literal["project", "project_index", "section", "company"]
    if meta.kind == "project_index":
        kind = "project_index"
    elif meta.kind in {"section", "home"}:
        kind = "section"
    elif route in _PROJECT_ROUTES or is_listing:
        kind = "project"
    else:
        kind = "company"
    title = _page_title(html) or body.split("\n", 1)[0]
    return Page(
        id=_record_id(kind, meta.url),
        source=Source.DARGLOBAL,
        url=meta.url,
        scraped_at=meta.fetched_at,
        kind=kind,
        title=title,
        body=body,
        faqs=faqs_from_json_ld(html),
    )


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def _page_title(html: str) -> str | None:
    match = _TITLE.search(html)
    if not match:
        return None
    title = html_to_text(match.group(1))
    return title.split(" | ")[0].strip() if title else None


def parse_page(meta: FetchMeta, html: str) -> DarGlobalRecord | None:
    """Dispatch one stored page to its parser. None = nothing worth keeping."""
    data = next_data(html)
    route: str = data.get("page", "")
    props: dict[str, Any] = data.get("props", {}).get("pageProps", {})
    if meta.kind == "blog":
        return parse_blog(meta, props)
    if meta.kind == "press":
        return parse_press(meta, props)
    if meta.kind == "insight":
        return parse_insight(meta, props)
    if meta.kind == "partner":
        return parse_partner(meta, props)
    if "projectDetailsData" in props:
        return parse_project(meta, html, props)
    if (
        route == "/one-of-one/[slug]"
        and isinstance(props.get("collectionsData"), list)
        and (page := parse_one_of_one(meta, data)) is not None
    ):
        return page
    return parse_generic(meta, html, data, route)


def parse_one_of_one(meta: FetchMeta, data: dict[str, Any]) -> Page | None:
    """One-of-one pages embed the whole 8-property collection; keep only this page's item."""
    slug = str((data.get("query") or {}).get("slug") or _slug(meta.url).split("/")[-1]).lower()
    items = [_unwrap(item) for item in data["props"]["pageProps"]["collectionsData"]]
    item = next((i for i in items if str(i.get("slug", "")).strip("/").lower() == slug), None)
    if item is None:
        return None
    title = _str(item.get("title"))
    body = cms_text({k: v for k, v in item.items() if k not in {"slug", "contentPosition"}})
    if not title or not body:
        return None
    return Page(
        id=_record_id("project", meta.url),
        source=Source.DARGLOBAL,
        url=meta.url,
        scraped_at=meta.fetched_at,
        kind="project",
        title=title,
        body=body,
    )
