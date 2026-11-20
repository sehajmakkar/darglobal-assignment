from dgbot.scraping.text import blocks_to_text, cms_text, html_to_text


def test_html_to_text_keeps_structure_and_drops_markup() -> None:
    html = (
        "<html><body><h2>Why Dubai</h2><p style='x'>Tax-free <b>returns</b>.</p>"
        "<ul><li>Golden visa</li><li>Growth</li></ul><script>track()</script>"
        "<p>Last&nbsp;para</p></body></html>"
    )
    assert html_to_text(html) == (
        "Why Dubai\n\nTax-free returns.\n\n- Golden visa\n\n- Growth\n\nLast para"
    )


def test_html_to_text_plain_string_and_empty() -> None:
    assert html_to_text("  just   text ") == "just text"
    assert html_to_text("Apartments &amp; Villas &#38; Dubai") == "Apartments & Villas & Dubai"
    assert html_to_text("") is None
    assert html_to_text(None) is None


def test_blocks_to_text() -> None:
    blocks = [
        {"type": "paragraph", "children": [{"type": "text", "text": "First "}, {"text": "para."}]},
        {
            "type": "list",
            "children": [{"children": [{"text": "one"}]}, {"children": [{"text": "two"}]}],
        },
    ]
    assert blocks_to_text(blocks) == "First para.\n\n- one\n- two"


def test_cms_text_collects_content_and_skips_chrome_media_links() -> None:
    data = {
        "globalData": {"menu": [{"title": "Home"}]},
        "SEO": {"metaTitle": "SEO only"},
        "pageData": {
            "id": 7,
            "Heading": "Pagani Residences",
            "HeroBanner": {"data": {"title": "banner"}},
            "image": {"formats": {}, "name": "hero.jpg"},
            "AboutDetailsType": [
                {"name": "Status", "value": "Under construction"},
                {"name": "Status", "value": "Under construction"},
            ],
            "button": {"label": "Register", "href": "/register", "link": "https://x"},
            "description": "<p>Hand-built <em>details</em>.</p>",
            "answer": [{"type": "paragraph", "children": [{"text": "Blocks work too."}]}],
        },
    }
    assert cms_text(data) == (
        "Pagani Residences\nStatus\nUnder construction\nHand-built details.\nBlocks work too."
    )


def test_html_to_text_decodes_double_encoded_entities() -> None:
    # DarGlobal's CMS sometimes double-encodes: "&amp;amp;" must still become "&".
    assert html_to_text("<p>Trump International Hotel &amp;amp; Tower</p>") == (
        "Trump International Hotel & Tower"
    )
