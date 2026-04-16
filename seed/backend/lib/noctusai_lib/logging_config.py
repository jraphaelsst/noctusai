"""
Structured logging configuration for all NoctusAI APIs.

Provides JSON logging format for production and human-readable format
for development. Uses the PF-style _IGNORED_KEYS set for cleaner
filtering, and timezone-aware UTC timestamps.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from noctusai_lib.middleware import get_correlation_id

# Keys from LogRecord.__dict__ that are internal and should not appear
# in the structured output.
_IGNORED_KEYS = {
    "name", "msg", "args", "created", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs",
    "pathname", "process", "processName", "relativeCreated",
    "stack_info", "exc_info", "exc_text", "thread", "threadName",
    "message", "taskName",
}


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.123456+00:00",
        "level": "INFO",
        "logger": "app.routers.clientes",
        "message": "Request completed",
        "correlation_id": "abc-123",
        ...extra_fields
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if available
        correlation_id = get_correlation_id()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add extra fields from the log record
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in _IGNORED_KEYS:
                    log_data[key] = value

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class HumanReadableFormatter(logging.Formatter):
    """
    Human-readable log formatter for development.

    Output format:
    2024-01-15 10:30:00 | INFO     | app.routers.clientes | Request completed | correlation_id=abc-123
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        correlation_id = get_correlation_id()

        base = f"{timestamp} | {record.levelname:8} | {record.name} | {record.getMessage()}"

        # Add correlation ID if available
        if correlation_id:
            base += f" | correlation_id={correlation_id}"

        # Add extra fields
        extra_parts = []
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in _IGNORED_KEYS and key != "correlation_id":
                    extra_parts.append(f"{key}={value}")

        if extra_parts:
            base += f" | {', '.join(extra_parts)}"

        # Add exception info if present
        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"

        return base


def configure_logging(
    debug: bool = True,
    json_logs: bool = False,
    app_name: str = "noctusai",
) -> None:
    """
    Configure application logging.

    Args:
        debug: If True, use DEBUG level; otherwise INFO
        json_logs: If True, use JSON format; otherwise human-readable
        app_name: Application name for identification in logs (currently
                  reserved for future use in structured output)
    """
    # Determine log level
    level = logging.DEBUG if debug else logging.INFO

    # Choose formatter
    if json_logs:
        formatter = JSONFormatter()
    else:
        formatter = HumanReadableFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)
