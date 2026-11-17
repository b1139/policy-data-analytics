"""Structured logging configuration with request correlation ID support."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

# Context variable tracking current request correlation ID across async tasks
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Retrieve the current request correlation ID or empty string.

    Returns:
        str: Current correlation ID or empty string.
    """
    return request_id_ctx.get()


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request correlation ID into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach request_id attribute to the log record."""
        record.request_id = request_id_ctx.get() or "-"  # type: ignore[attr-defined]
        return True


class JSONLogFormatter(logging.Formatter):
    """Formatter producing structured JSON log lines for observability."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a LogRecord as a single-line JSON string.

        Args:
            record: The LogRecord to format.

        Returns:
            str: JSON-encoded log line.
        """
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-") or "-",
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload)


def setup_logging(level: str | None = None, use_json: bool = True) -> None:
    """Configure application-wide structured logging.

    Args:
        level: Optional log level override (e.g., 'DEBUG', 'INFO').
        use_json: If True, log in JSON lines; otherwise standard human-readable text.
    """
    log_level = (level or settings.LOG_LEVEL).upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.addFilter(RequestIdFilter())

    if use_json:
        handler.setFormatter(JSONLogFormatter())
    else:
        fmt = "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt=fmt))

    root_logger.addHandler(handler)

    # Suppress verbose noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
