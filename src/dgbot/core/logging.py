"""Logging setup: JSON lines in prod (machine-parseable), readable text in dev."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from dgbot.core.config import Settings

_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)))


class JsonFormatter(logging.Formatter):
    """Render records as one JSON object per line, including `extra=` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _RESERVED})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    """Configure the root logger once at process start."""
    handler = logging.StreamHandler(sys.stdout)
    if settings.env == "prod":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
        )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)
