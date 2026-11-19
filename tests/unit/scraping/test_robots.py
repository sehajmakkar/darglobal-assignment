from pathlib import Path

import pytest

from dgbot.scraping.robots import RobotsPolicy

UA = "DarGlobalAssignmentBot/0.1"
DARGLOBAL_ROBOTS = (Path(__file__).parents[2] / "fixtures/darglobal/robots.txt").read_text()


@pytest.fixture
def darglobal() -> RobotsPolicy:
    return RobotsPolicy.from_text(DARGLOBAL_ROBOTS, UA)


@pytest.mark.parametrize(
    "url",
    [
        "https://darglobal.co.uk/",
        "https://darglobal.co.uk/the-astera",
        "https://darglobal.co.uk/blog/some-post",
        "https://darglobal.co.uk/partners/aston-martin",
    ],
)
def test_darglobal_content_paths_are_allowed(darglobal: RobotsPolicy, url: str) -> None:
    assert darglobal.allowed(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://darglobal.co.uk/sitemap_index.xml",
        "https://darglobal.co.uk/the-astera?utm_source=newsletter",  # wildcard rule
        "https://darglobal.co.uk/?s=villas",
        "https://darglobal.co.uk/shop?wc-ajax=get_refreshed_fragments",
    ],
)
def test_darglobal_disallowed_paths(darglobal: RobotsPolicy, url: str) -> None:
    assert not darglobal.allowed(url)


def test_missing_robots_4xx_means_allow_all() -> None:
    assert RobotsPolicy.from_status(404, UA).allowed("https://cdn.wasalt.sa/sitemap/x.xml.gz")


@pytest.mark.parametrize("status", [500, 503])
def test_unreachable_robots_5xx_means_disallow_all(status: int) -> None:
    assert not RobotsPolicy.from_status(status, UA).allowed("https://example.com/")
