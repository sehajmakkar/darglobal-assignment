import json
from typing import Any

from fastapi.testclient import TestClient

from dgbot import __version__
from dgbot.api.app import create_app
from dgbot.core.config import Settings
from dgbot.core.errors import DgbotError, LLMQuotaExceededError
from dgbot.llm.fake import FakeLLMClient
from tests.support.runtime import fake_runtime


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, env="test", **overrides)  # type: ignore[arg-type]


def _client(llm: FakeLLMClient | None = None, **settings: object) -> TestClient:
    app = create_app(_settings(**settings), runtime_factory=lambda _: fake_runtime(llm))
    return TestClient(app)


def _events(body: str) -> list[tuple[str, Any]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_health_reports_ready_and_index() -> None:
    with _client() as client:
        body = client.get("/api/health").json()

    assert body["status"] == "ok" and body["version"] == __version__ and body["env"] == "test"
    assert body["ready"] is True and body["index"]["embedding_model"] == "fake-dense"


def test_without_an_index_health_is_not_ready_and_chat_is_503() -> None:
    def broken(_: Settings) -> object:
        raise DgbotError("no search index at data/index")

    app = create_app(_settings(), runtime_factory=broken)  # type: ignore[arg-type]
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        chat = client.post("/api/chat", json={"message": "hi"})

    assert health["ready"] is False and "no search index" in health["detail"]
    assert chat.status_code == 503


def test_root_serves_the_frontend_page() -> None:
    with _client() as client:
        response = client.get("/")
    assert response.status_code == 200 and "text/html" in response.headers["content-type"]


def test_unknown_api_route_is_404_not_the_frontend() -> None:
    with _client() as client:
        assert client.get("/api/does-not-exist").status_code == 404


def test_chat_streams_sources_then_tokens_then_done() -> None:
    with _client() as client:
        response = client.post("/api/chat", json={"message": "Tell me about The Astera"})

    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    names = [name for name, _ in events]
    assert names[0] == "sources" and names[-1] == "done" and "token" in names
    sources = events[0][1]["sources"]
    assert sources[0]["n"] == 1 and sources[0]["url"].startswith("https://example.test/")
    done = events[-1][1]
    assert "[1]" in done["answer"] and done["sources"][0]["cited"] is True
    assert done["model"] == "fake/model" and done["lang"] == "en"


def test_chat_json_mode() -> None:
    with _client() as client:
        body = client.post("/api/chat", json={"message": "What is DG1?", "stream": False}).json()
    assert body["answer"] and body["sources"] and body["cached"] is False


def test_quota_exhaustion_is_an_error_event_not_a_crash() -> None:
    llm = FakeLLMClient(error=LLMQuotaExceededError("all keys used"))
    with _client(llm) as client:
        events = _events(client.post("/api/chat", json={"message": "What is DG1?"}).text)

    assert events[-1][0] == "error" and events[-1][1]["code"] == "quota"


def test_rate_limit_per_ip() -> None:
    with _client(rate_limit_per_minute=2) as client:
        codes = [
            client.post(
                "/api/chat",
                json={"message": f"q{i}", "stream": False},
                headers={"X-Forwarded-For": "203.0.113.9"},
            ).status_code
            for i in range(3)
        ]
        other = client.post(
            "/api/chat",
            json={"message": "q", "stream": False},
            headers={"X-Forwarded-For": "198.51.100.1"},
        )
    assert codes == [200, 200, 429]
    assert other.status_code == 200  # limits are per client IP


def test_input_limits() -> None:
    with _client() as client:
        too_long = client.post("/api/chat", json={"message": "x" * 1001})
        empty = client.post("/api/chat", json={"message": ""})
        history = client.post(
            "/api/chat", json={"message": "hi", "history": [{"role": "user", "content": "a"}] * 11}
        )
    assert {too_long.status_code, empty.status_code, history.status_code} == {422}
