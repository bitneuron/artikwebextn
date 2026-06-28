"""Structured (JSON) logging with named channels: app, scheduler, notification,
audit, security, error. One formatter, easy to ship to CloudWatch later."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_CHANNELS = ("app", "scheduler", "notification", "audit", "security", "error")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "channel": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for k, v in getattr(record, "extra_fields", {}).items():
            payload[k] = v
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for ch in _CHANNELS:
        logging.getLogger(ch).setLevel(level)


def get_logger(channel: str = "app") -> logging.Logger:
    return logging.getLogger(channel if channel in _CHANNELS else "app")


def log_event(channel: str, message: str, level: int = logging.INFO, **fields) -> None:
    logger = get_logger(channel)
    logger.log(level, message, extra={"extra_fields": fields})
