"""Opt-in smoke test against the real OpenRouter API. Uses 1 request of the daily quota.

Run with: uv run pytest -m live -s
"""

import pytest
from openai import AsyncOpenAI

from dgbot.core.config import Settings

pytestmark = pytest.mark.live


async def test_primary_free_model_answers() -> None:
    settings = Settings()
    if not settings.openrouter_api_keys:
        pytest.skip("no OpenRouter key configured")

    client = AsyncOpenAI(
        api_key=settings.openrouter_api_keys[0].get_secret_value(),
        base_url=settings.openrouter_base_url,
        timeout=settings.llm_timeout_s,
        default_headers={"HTTP-Referer": settings.app_url, "X-Title": settings.app_title},
    )
    response = await client.chat.completions.create(
        model=settings.llm_models[0],
        # OpenRouter-specific: server-side fallback to the remaining models (D-010), and
        # low reasoning effort so reasoning models don't spend the whole budget thinking.
        extra_body={"models": settings.llm_models, "reasoning": {"effort": "low"}},
        messages=[{"role": "user", "content": "Reply with exactly the word: pong"}],
        # Reasoning tokens count against max_tokens; 20 was fully consumed by reasoning (C-006).
        max_tokens=400,
    )

    text = (response.choices[0].message.content or "").strip().lower()
    print(f"\nserved model: {response.model} | reply: {text!r} | usage: {response.usage}")
    assert "pong" in text
