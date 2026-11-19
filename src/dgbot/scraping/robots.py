"""robots.txt policy, following RFC 9309 for unreachable files.

We use Protego (Scrapy's parser) because DarGlobal's rules use `*` and `$` wildcards,
which the standard library's `urllib.robotparser` does not understand.
"""

from __future__ import annotations

from dataclasses import dataclass

from protego import Protego


@dataclass(frozen=True)
class RobotsPolicy:
    """Answers "may this user agent fetch this URL?" for one host."""

    user_agent: str
    _parser: Protego | None
    _allow_all: bool

    @classmethod
    def from_text(cls, text: str, user_agent: str) -> RobotsPolicy:
        return cls(user_agent, Protego.parse(text), _allow_all=False)

    @classmethod
    def from_status(cls, status: int, user_agent: str) -> RobotsPolicy:
        """Policy when robots.txt couldn't be read as text.

        RFC 9309 §2.3.1.3-4: 4xx ("unavailable") → crawling allowed; 5xx or network
        error ("unreachable") → assume complete disallow.
        """
        if 400 <= status < 500:
            return cls(user_agent, None, _allow_all=True)
        return cls(user_agent, None, _allow_all=False)

    def allowed(self, url: str) -> bool:
        if self._allow_all:
            return True
        if self._parser is None:
            return False
        return bool(self._parser.can_fetch(url, self.user_agent))

    @property
    def sitemaps(self) -> list[str]:
        return list(self._parser.sitemaps) if self._parser else []
