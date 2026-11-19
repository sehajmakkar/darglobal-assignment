"""Cross-record fixes in the process step (brands, duplicates)."""

from datetime import UTC, datetime

from dgbot.domain.models import Page, Partner, Project, ProjectRef, Source
from dgbot.scraping.process import ProcessReport, _assign_brands, _dedupe_pages, _dedupe_projects

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def _project(name: str, url: str, **kw: object) -> Project:
    return Project(
        id=f"darglobal:project:{url}",
        source=Source.DARGLOBAL,
        url=url,
        scraped_at=NOW,
        name=name,
        **kw,
    )


def _partner(name: str, *project_urls: str) -> Partner:
    return Partner(
        id=f"darglobal:partner:{name}",
        source=Source.DARGLOBAL,
        url="https://x",
        scraped_at=NOW,
        name=name,
        projects=[ProjectRef(name="p", url=u) for u in project_urls],
    )


def test_brand_from_partner_page_then_alias_then_none() -> None:
    projects = [
        _project("Tierra Viva", "https://darglobal.co.uk/tierra-viva"),
        _project("Trump Cliff Villas", "https://darglobal.co.uk/cliff"),
        _project("DG1", "https://darglobal.co.uk/dg1"),
    ]
    partners = [
        _partner(
            "Automobili Lamborghini", "https://darglobal.co.uk/Tierra-Viva"
        ),  # case-insensitive
        _partner("The Trump Organization"),
    ]

    brands = [p.brand_partner for p in _assign_brands(projects, partners)]

    assert brands == ["Automobili Lamborghini", "The Trump Organization", None]


def test_duplicate_projects_keep_the_fuller_record() -> None:
    report = ProcessReport()
    thin = _project("Trump Tower", "https://darglobal.co.uk/a")
    full = _project("TRUMP TOWER", "https://darglobal.co.uk/b", city="Dubai", country="UAE")

    kept = _dedupe_projects([thin, full], report)

    assert [p.url for p in kept] == ["https://darglobal.co.uk/b"]
    assert "duplicate project" in report.notes[0]


def test_pages_with_identical_text_are_collapsed() -> None:
    def page(url: str, body: str) -> Page:
        return Page(
            id=url,
            source=Source.DARGLOBAL,
            url=url,
            scraped_at=NOW,
            kind="project_index",
            title="t",
            body=body,
        )

    kept = _dedupe_pages(
        [
            page("https://d/projects/uae", "catalogue"),
            page("https://d/projects", "catalogue"),
            page("https://d/projects/uk", "other"),
        ],
        ProcessReport(),
    )

    assert sorted(p.url for p in kept) == ["https://d/projects", "https://d/projects/uk"]
