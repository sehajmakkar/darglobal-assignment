import json
import threading
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from dgbot import __version__
from dgbot.api.app import create_app
from dgbot.api.dependencies import Runtime
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
        body = client.get("/api/health?wait=5").json()

    assert body["status"] == "ok" and body["version"] == __version__ and body["env"] == "test"
    assert body["ready"] is True and body["warming_up"] is False
    assert body["index"]["embedding_model"] == "fake-dense"


def test_without_an_index_health_is_not_ready_and_chat_is_503() -> None:
    def broken(_: Settings) -> object:
        raise DgbotError("no search index at data/index")

    app = create_app(_settings(), runtime_factory=broken)  # type: ignore[arg-type]
    with TestClient(app) as client:
        chat = client.post("/api/chat", json={"message": "hi"})  # waits for loading to end
        health = client.get("/api/health").json()

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


# ── Cold start: listen first, load the model in the background (C-030) ──────────


def _slow_runtime(gate: threading.Event) -> Callable[[Settings], Runtime]:
    def factory(_: Settings) -> Runtime:
        assert gate.wait(10), "test gate never opened"
        return fake_runtime(None)

    return factory


def test_ui_and_health_answer_while_the_model_is_still_loading() -> None:
    gate = threading.Event()
    app = create_app(_settings(), runtime_factory=_slow_runtime(gate))
    with TestClient(app) as client:
        page = client.get("/")
        loading = client.get("/api/health").json()
        gate.set()
        ready = client.get("/api/health?wait=5").json()

    assert page.status_code == 200
    assert loading["ready"] is False and loading["warming_up"] is True
    assert "warming up" in loading["detail"]
    assert ready["ready"] is True and ready["warming_up"] is False


def test_a_question_sent_during_warm_up_waits_instead_of_failing() -> None:
    gate = threading.Event()
    app = create_app(_settings(), runtime_factory=_slow_runtime(gate))
    with TestClient(app) as client:
        threading.Timer(0.2, gate.set).start()
        response = client.post(
            "/api/chat", json={"message": "What is The Astera?", "stream": False}
        )

    assert response.status_code == 200 and response.json()["answer"]


def test_warm_up_longer_than_the_wait_limit_is_503() -> None:
    gate = threading.Event()
    app = create_app(_settings(startup_wait_seconds=0.1), runtime_factory=_slow_runtime(gate))
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hi"})
        gate.set()

    assert response.status_code == 503 and "warming up" in response.json()["detail"]


def test_an_unexpected_loading_crash_is_reported_not_hung() -> None:
    def crash(_: Settings) -> Runtime:
        raise RuntimeError("boom")

    app = create_app(_settings(), runtime_factory=crash)
    with TestClient(app) as client:
        health = client.get("/api/health?wait=5").json()
        chat = client.post("/api/chat", json={"message": "hi"})

    assert health["ready"] is False and health["warming_up"] is False
    assert health["detail"] == "chat runtime failed to load"
    assert chat.status_code == 503
