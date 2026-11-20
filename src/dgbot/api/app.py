"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from dgbot import __version__
from dgbot.api.dependencies import Runtime, build_runtime
from dgbot.api.ratelimit import RateLimiter
from dgbot.api.routes import chat, health
from dgbot.core.config import Settings, get_settings
from dgbot.core.errors import DgbotError
from dgbot.core.logging import configure_logging

logger = logging.getLogger(__name__)

RuntimeFactory = Callable[[Settings], Runtime]

WARMING_UP = "warming up: loading the search model"


def create_app(
    settings: Settings | None = None, runtime_factory: RuntimeFactory | None = None
) -> FastAPI:
    """Build the app. Tests pass `settings` and a `runtime_factory` with fakes."""
    settings = settings or get_settings()
    configure_logging(settings)
    factory = runtime_factory or build_runtime

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("dgbot %s starting (env=%s)", __version__, settings.env)
        # Listen first, load the search model in a worker thread: the UI is served at once
        # after a cold start instead of a blank tab for ~40 s (C-030).
        loading = asyncio.create_task(_load_runtime(app, factory, settings))
        yield
        loading.cancel()
        if app.state.runtime is not None:
            app.state.runtime.close()
        logger.info("dgbot shutting down")

    app = FastAPI(
        title=settings.app_title,
        version=__version__,
        lifespan=lifespan,
        # Interactive docs are handy for reviewers; they expose nothing secret.
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.runtime = None
    app.state.runtime_error = WARMING_UP
    app.state.runtime_loaded = asyncio.Event()
    app.state.rate_limiter = RateLimiter(
        settings.rate_limit_per_minute, settings.rate_limit_per_day
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    # Mounted last so /api/* routes win over static files.
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app


async def _load_runtime(app: FastAPI, factory: RuntimeFactory, settings: Settings) -> None:
    """Build the runtime off the event loop; always release waiters, whatever happens."""
    started = time.perf_counter()
    try:
        app.state.runtime = await anyio.to_thread.run_sync(
            factory, settings, abandon_on_cancel=True
        )
        app.state.runtime_error = None
        logger.info("chat runtime ready in %.1f s", time.perf_counter() - started)
    except DgbotError as exc:  # still serve /api/health and the UI; chat returns 503
        logger.error("chat runtime not available: %s", exc)
        app.state.runtime_error = str(exc)
    except Exception:  # a background task's crash would otherwise vanish silently
        logger.exception("chat runtime failed to load")
        app.state.runtime_error = "chat runtime failed to load"
    finally:
        app.state.runtime_loaded.set()
