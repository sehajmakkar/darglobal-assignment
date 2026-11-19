"""Run the server: `python -m dgbot.api`. Host and port come from Settings ($PORT)."""

from __future__ import annotations

import uvicorn

from dgbot.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "dgbot.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        # Don't let uvicorn install its own handlers: its loggers propagate to the root
        # logger that core/logging.py configures, so all output shares one format.
        log_config=None,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
