import pytest

from dgbot.core.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's real shell env from leaking into these tests."""
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_API_KEYS", "DGBOT_LLM_MODELS"):
        monkeypatch.delenv(name, raising=False)


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_single_api_key_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "key-a")

    assert [k.get_secret_value() for k in _settings().openrouter_api_keys] == ["key-a"]


def test_csv_env_vars_are_split_and_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEYS", "key-a, key-b ,,")
    monkeypatch.setenv("DGBOT_LLM_MODELS", "m1:free,m2:free")

    settings = _settings()

    assert [k.get_secret_value() for k in settings.openrouter_api_keys] == ["key-a", "key-b"]
    assert settings.llm_models == ["m1:free", "m2:free"]


def test_api_keys_are_never_rendered_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-super-secret")

    assert "sk-or-super-secret" not in repr(_settings())


def test_scraper_rate_limit_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DGBOT_SCRAPER_MAX_RPS", "10")

    with pytest.raises(ValueError):
        _settings()
