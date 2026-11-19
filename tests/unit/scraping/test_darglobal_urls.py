import pytest

from dgbot.scraping.sources.darglobal.urls import (
    UrlKind,
    classify,
    is_challenge_page,
    is_on_site,
    plan_fetch_order,
)

BASE = "https://darglobal.co.uk"


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("/", UrlKind.HOME),
        ("/the-astera", UrlKind.PAGE),
        ("/about", UrlKind.PAGE),
        ("/one-of-one/project-pagani", UrlKind.PAGE),
        ("/rayana/trump-mansions", UrlKind.PAGE),
        ("/partners/aston-martin", UrlKind.PARTNER),
        ("/projects/properties-in-uae/villas", UrlKind.PROJECT_INDEX),
        ("/blog", UrlKind.SECTION),
        ("/blog/exploring-dubais-art-scene", UrlKind.BLOG),
        ("/press/dar-global-expands-saudi-portfolio", UrlKind.PRESS),
        ("/insights/oman-gated-communities", UrlKind.INSIGHT),
        ("/thank-you", UrlKind.SKIP),
        ("/bookYourUnit", UrlKind.SKIP),
        ("/pay-online/status", UrlKind.SKIP),
        ("/landingpage/newStaticLandingPageHtml", UrlKind.SKIP),
        ("/some-project-duplicate-27740", UrlKind.SKIP),
    ],
)
def test_classify(path: str, kind: UrlKind) -> None:
    assert classify(BASE + path) is kind


def test_fetch_order_puts_projects_first_blog_last_and_drops_skips() -> None:
    urls = [f"{BASE}/blog/a", f"{BASE}/press/b", f"{BASE}/thank-you", f"{BASE}/the-astera"]

    order = [kind for _, kind in plan_fetch_order(urls)]

    assert order == [UrlKind.PAGE, UrlKind.PRESS, UrlKind.BLOG]


def test_detects_incapsula_challenge_page() -> None:
    challenge = (
        '<html><head><META NAME="robots" CONTENT="noindex,nofollow">'
        '<script src="/_Incapsula_Resource?SWJIYLWA=5074a7"></script></head></html>'
    )
    assert is_challenge_page(challenge)


def test_real_page_is_not_a_challenge_even_if_it_mentions_captcha() -> None:
    real = "<html>" + "x" * 50_000 + "protected by reCAPTCHA</html>"
    assert not is_challenge_page(real)


@pytest.mark.parametrize(
    ("url", "on_site"),
    [
        ("https://darglobal.co.uk/the-astera", True),
        ("https://www.darglobal.co.uk/about", True),
        ("https://darglobal.thetalentpool.co.in/web/careers/", False),  # /careers redirect
        ("https://evil.example/darglobal.co.uk", False),
    ],
)
def test_is_on_site(url: str, on_site: bool) -> None:
    assert is_on_site(url) is on_site
