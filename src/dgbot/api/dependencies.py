"""Composition root: the one place that builds concrete implementations and hands them
to route handlers through FastAPI dependency injection (D-016).

Right now it only exposes settings; the retriever, LLM client and chat service are
wired here as their phases land.
"""

from __future__ import annotations

from fastapi import Request

from dgbot.core.config import Settings


def get_app_settings(request: Request) -> Settings:
    """Settings the app was created with (lets tests inject their own)."""
    settings: Settings = request.app.state.settings
    return settings
