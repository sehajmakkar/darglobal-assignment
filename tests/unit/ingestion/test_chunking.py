from datetime import UTC, date, datetime

from dgbot.domain.models import Article, Fact, Faq, Listing, Project, Source
from dgbot.ingestion.chunking import build_chunks, split_words

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def test_split_words_packs_paragraphs_with_overlap() -> None:
    text = "\n\n".join(" ".join(f"p{i}w{j}" for j in range(60)) for i in range(5))  # 5 x 60 words

    windows = split_words(text, chunk_words=130, overlap_words=10)

    assert all(len(w.split()) <= 140 for w in windows)
    assert windows[1].split()[:10] == windows[0].split()[-10:]  # overlap carried over
    assert "p4w59" in windows[-1]  # nothing lost at the end


def test_split_words_splits_one_huge_paragraph() -> None:
    windows = split_words(" ".join(f"w{i}" for i in range(500)), chunk_words=200, overlap_words=50)
    assert len(windows) >= 3 and all(len(w.split()) <= 250 for w in windows)


def test_project_card_details_and_one_chunk_per_faq() -> None:
    p = Project(
        id="darglobal:project:x",
        source=Source.DARGLOBAL,
        url="https://d/x",
        scraped_at=NOW,
        name="X Tower",
        location="Dubai, UAE",
        status="Ready",
        facts=[Fact(name="Location", value="Dubai, UAE"), Fact(name="Units", value="42")],
        faqs=[Faq(question="Q1?", answer="A1"), Faq(question="Q2?", answer="A2")],
    )
    chunks = build_chunks([p])

    sections = sorted(c.section for c in chunks)
    assert sections == ["card", "details", "faq", "faq"]
    card = next(c for c in chunks if c.section == "card")
    assert card.text.startswith("X Tower — DarGlobal project")
    assert card.text.count("Location:") == 1 and "Units: 42" in card.text
    assert "Prices are not published" in card.text  # D-037


def test_article_chunks_are_title_prefixed() -> None:
    a = Article(
        id="darglobal:blog:b",
        source=Source.DARGLOBAL,
        url="https://d/b",
        scraped_at=NOW,
        kind="blog",
        title="Why Dubai",
        published=date(2025, 1, 2),
        body="word " * 450,
    )
    chunks = build_chunks([a])

    assert len(chunks) >= 2
    assert all(c.text.startswith("Why Dubai — DarGlobal blog (2025-01-02)") for c in chunks)


def test_sitemap_listings_are_summarised_not_indexed_one_by_one() -> None:
    listings = [
        Listing(
            id=f"wasalt:listing:{i}",
            source=Source.WASALT,
            url=f"https://w/{i}",
            scraped_at=NOW,
            listing_id=str(i),
            purpose="sale",
            property_type="villa",
            area_sqm=300.0 + i,
            bedrooms=4,
        )
        for i in range(25)
    ]
    chunks = build_chunks(listings)

    assert {c.record_type for c in chunks} == {"summary"}
    stats = next(c for c in chunks if c.id == "wasalt:summary:type:sale:villa#summary-0")
    assert "Number of listings: 25." in stats.text and "4 bedrooms 100%" in stats.text


def test_duplicate_records_are_ignored() -> None:
    lst = Listing(
        id="wasalt:listing:1",
        source=Source.WASALT,
        url="https://w/1",
        scraped_at=NOW,
        listing_id="1",
        detail="page",
        purpose="rent",
        property_type="apartment",
        price=36000,
    )
    assert len([c for c in build_chunks([lst, lst]) if c.record_type == "listing"]) == 1


def test_wasalt_summaries_are_bilingual() -> None:
    from dgbot.domain.models import AreaCoverage

    area = AreaCoverage(
        id="wasalt:area:rent:apartments:riyadh-al-malqa",
        source=Source.WASALT,
        url="https://w/a",
        scraped_at=NOW,
        purpose="rent",
        property_type="apartment",
        city="Riyadh",
        district="Al Malqa",
    )
    chunks = build_chunks([area])

    city = next(c for c in chunks if c.id == "wasalt:summary:city:riyadh:rent#summary-0")
    assert "Al Malqa" in city.text
    assert "الرياض" in city.text and "للإيجار" in city.text and "شقق" in city.text  # D-042
    overview = next(c for c in chunks if c.record_id == "wasalt:summary:overview")
    assert "وصلت" in overview.text
