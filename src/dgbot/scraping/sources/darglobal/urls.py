"""DarGlobal URL classification for collection (not the final record type).

URL shape alone can't tell a project page (`/the-astera`) from a static page (`/about`):
both are single slugs. The Phase 2 parser decides from the page's JSON-LD (D-024). Here
we only need (a) what to skip and (b) a fetch order that gets the valuable pages first,
so an interrupted run still has the projects.
"""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit


class UrlKind(StrEnum):
    HOME = "home"
    PAGE = "page"  # project or static page — resolved in Phase 2
    PARTNER = "partner"
    PROJECT_INDEX = "project_index"  # /projects/properties-in-<country>[/<type>]
    SECTION = "section"  # /blog, /press, /partners ... listing pages
    PRESS = "press"
    INSIGHT = "insight"
    BLOG = "blog"
    SKIP = "skip"


# Forms, payment/booking flows, thank-you pages and stray landing pages: no knowledge.
_SKIP_FIRST_SEGMENTS = frozenset(
    {
        "thank-you",
        "bookyourunit",
        "internship-application",
        "new-home-page",
        "pay-online",
        "landingpage",
        "landing-page",
    }
)
_SECTIONS = frozenset({"blog", "press", "insights", "partners", "projects", "one-of-one"})
# Sub-paths that hold project pages (e.g. /one-of-one/project-pagani).
_PROJECT_GROUPS = frozenset({"one-of-one", "rayana", "amaya", "trump-plaza"})
_ARTICLES = {"blog": UrlKind.BLOG, "press": UrlKind.PRESS, "insights": UrlKind.INSIGHT}

PRIORITY: dict[UrlKind, int] = {
    UrlKind.HOME: 0,
    UrlKind.PAGE: 0,
    UrlKind.PARTNER: 0,
    UrlKind.PROJECT_INDEX: 1,
    UrlKind.SECTION: 1,
    UrlKind.PRESS: 2,
    UrlKind.INSIGHT: 2,
    UrlKind.BLOG: 3,
    UrlKind.SKIP: 9,
}


def classify(url: str) -> UrlKind:
    path = urlsplit(url).path.strip("/")
    if not path:
        return UrlKind.HOME
    segments = path.split("/")
    first = segments[0].lower()
    if first in _SKIP_FIRST_SEGMENTS or "-duplicate-" in path.lower():
        return UrlKind.SKIP
    if len(segments) == 1:
        return UrlKind.SECTION if first in _SECTIONS else UrlKind.PAGE
    if first in _ARTICLES:
        return _ARTICLES[first]
    if first == "partners":
        return UrlKind.PARTNER
    if first == "projects":
        return UrlKind.PROJECT_INDEX
    if first in _PROJECT_GROUPS:
        return UrlKind.PAGE
    return UrlKind.PAGE


def plan_fetch_order(urls: list[str]) -> list[tuple[str, UrlKind]]:
    """Non-skipped URLs with their kind, most valuable first (stable within a tier)."""
    classified = [(url, classify(url)) for url in urls]
    kept = [(url, kind) for url, kind in classified if kind is not UrlKind.SKIP]
    return sorted(kept, key=lambda item: PRIORITY[item[1]])


_SITE_HOSTS = frozenset({"darglobal.co.uk", "www.darglobal.co.uk"})


def is_on_site(url: str) -> bool:
    """False when a page redirected off DarGlobal (e.g. /careers → a third-party ATS).

    We only store DarGlobal's own pages; other domains are out of scope.
    """
    return urlsplit(url).netloc.lower() in _SITE_HOSTS


_CHALLENGE_MARKERS = (
    "_incapsula_resource",
    "incident id",
    "request unsuccessful",
    "captcha",
    "access denied",
)
_MAX_CHALLENGE_PAGE = 20_000


def is_challenge_page(html: str) -> bool:
    """True for Incapsula's bot-check / block pages (small pages carrying its markers).

    Real DarGlobal pages are 300 KB+; the challenge page we saw was 212 bytes (C-003).
    """
    return len(html) < _MAX_CHALLENGE_PAGE and any(m in html.lower() for m in _CHALLENGE_MARKERS)
