from fastapi.testclient import TestClient

from dgbot import __version__
from dgbot.api.app import create_app
from dgbot.core.config import Settings


def _client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, env="test")))


def test_health_reports_ok_and_version() -> None:
    response = _client().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "env": "test"}


def test_root_serves_the_frontend_page() -> None:
    response = _client().get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_unknown_api_route_is_404_not_the_frontend() -> None:
    assert _client().get("/api/does-not-exist").status_code == 404
