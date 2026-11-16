"""Structured JSON logging to stdout."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from raahat.config import Settings

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    if getattr(root, "_raahat_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # Provider clients log request URLs at INFO; keep them out of the log.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True
    root._raahat_configured = True  # type: ignore[attr-defined]
