"""
Structured logging configuration for the Personal Finance API.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from app.middleware import get_correlation_id

_IGNORED_KEYS = {
    "name", "msg", "args", "created", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs",
    "pathname", "process", "processName", "relativeCreated",
    "stack_info", "exc_info", "exc_text", "thread", "threadName",
    "message", "taskName",
}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            log_data["correlation_id"] = correlation_id
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in _IGNORED_KEYS:
                    log_data[key] = value
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, default=str)


class HumanReadableFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        correlation_id = get_correlation_id()
        base = f"{timestamp} | {record.levelname:8} | {record.name} | {record.getMessage()}"
        if correlation_id:
            base += f" | correlation_id={correlation_id}"
        extra_parts = []
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in _IGNORED_KEYS and key != "correlation_id":
                    extra_parts.append(f"{key}={value}")
        if extra_parts:
            base += f" | {', '.join(extra_parts)}"
        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"
        return base


def configure_logging(debug: bool = True, json_logs: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    formatter = JSONFormatter() if json_logs else HumanReadableFormatter()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
