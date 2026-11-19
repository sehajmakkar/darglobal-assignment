"""Exception hierarchy.

Layers raise specific subclasses; the API layer maps them to HTTP responses.
"""

from __future__ import annotations


class DgbotError(Exception):
    """Base class for all application errors."""


class ConfigError(DgbotError):
    """Settings are missing or invalid for the requested operation."""


class FetchError(DgbotError):
    """A request kept failing after all retries (network error, 5xx, 429)."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


class LLMError(DgbotError):
    """Base for LLM-provider failures; the API maps these to user-facing messages."""


class LLMQuotaExceededError(LLMError):
    """Every configured key hit the provider's daily/rate limit (D-015)."""


class LLMUnavailableError(LLMError):
    """No model produced an answer (timeouts, provider errors, empty replies)."""


class SourceBlockedError(DgbotError):
    """A source site refused access (bot protection, 403, robots.txt disallow).

    Per D-004 we never try to circumvent this: callers log it and move on.
    """

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason
