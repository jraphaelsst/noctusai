"""
Structured logging configuration for all NoctusAI APIs.

Provides JSON logging format for production and human-readable format
for development. Uses the PF-style _IGNORED_KEYS set for cleaner
filtering, and timezone-aware UTC timestamps.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict

# Import from the dep-free `primitives._correlation` module — NOT from
# `api.middleware` which pulls in fastapi + starlette and makes
# `logging_config` unimportable in CLI / MCP-toolkit contexts.
from noctusai_lib.primitives._correlation import get_correlation_id

# Keys from LogRecord.__dict__ that are internal and should not appear
# in the structured output.
_IGNORED_KEYS = {
    "name", "msg", "args", "created", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs",
    "pathname", "process", "processName", "relativeCreated",
    "stack_info", "exc_info", "exc_text", "thread", "threadName",
    "message", "taskName",
}


class _JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.123456+00:00",
        "level": "INFO",
        "app": "core",
        "logger": "app.routers.clientes",
        "message": "Request completed",
        "correlation_id": "abc-123",
        ...extra_fields
    }
    """

    def __init__(self, app_name: str = "noctusai") -> None:
        super().__init__()
        self.app_name = app_name

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "app": self.app_name,
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


class _HumanReadableFormatter(logging.Formatter):
    """
    Human-readable log formatter for development.

    Output format:
    2024-01-15 10:30:00 | INFO     | [core] app.routers.clientes | Request completed | correlation_id=abc-123
    """

    def __init__(self, app_name: str = "noctusai") -> None:
        super().__init__()
        self.app_name = app_name

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        correlation_id = get_correlation_id()

        base = f"{timestamp} | {record.levelname:8} | [{self.app_name}] {record.name} | {record.getMessage()}"

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
    stream: Any = None,
) -> None:
    """
    Configure application logging.

    Args:
        debug: If True, use DEBUG level; otherwise INFO
        json_logs: If True, use JSON format; otherwise human-readable
        app_name: Application name baked into every log record. JSON output
                  includes it as `"app": app_name`; human-readable prepends
                  it as `[<app_name>]` so multi-product log streams stay
                  parsable.
        stream: Optional stream to log to. Defaults to `sys.stdout` for
                backend products (uvicorn separately handles request I/O).
                Pass `sys.stderr` for stdio-protocol consumers like MCP
                servers, where stdout is the protocol channel and any
                non-JSON byte breaks the contract.
    """
    # Determine log level
    level = logging.DEBUG if debug else logging.INFO

    # Choose formatter — pass app_name so records carry it
    if json_logs:
        formatter = _JSONFormatter(app_name=app_name)
    else:
        formatter = _HumanReadableFormatter(app_name=app_name)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers — close before remove so FileHandler /
    # SocketHandler / SysLogHandler don't leak file descriptors on repeated
    # calls. StreamHandler.close() is a no-op so it's safe to call uniformly.
    _bootstrap_log = logging.getLogger(__name__)
    for handler in root_logger.handlers[:]:
        try:
            handler.close()
        except Exception as exc:
            # Handler already closed or doesn't expose close() — log at
            # debug level (drops to lastResort during reconfiguration; that's
            # fine, this is just a hygiene note).
            _bootstrap_log.debug("logging_config: handler.close() raised (%s); proceeding to remove", exc)
        root_logger.removeHandler(handler)

    # Add console handler — defaults to stdout, override with `stream=`
    # for stdio-protocol consumers (MCP server).
    console_handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)


def auto_configure_for_cli(
    app_name: str = "noctusai-cli",
    *,
    use_stderr: bool = False,
) -> None:
    """Configure logging for CLI / MCP-server entry-points.

    `configure_logging(...)` requires the caller to know `debug` and
    `json_logs` flags up front — that's the right shape for backend
    products which read settings via `pydantic-settings`. CLI tools (the
    MCP toolkit, ad-hoc scripts) don't have a settings object; they read
    env vars directly.

    Resolution rules:
      - `NOCTUSAI_DEBUG=1` (or `true` / `yes`) → debug level + human-readable formatter
      - Otherwise → INFO level + human-readable formatter (CLI default — JSON
        is hostile to humans reading `--validate` output)
      - `NOCTUSAI_JSON_LOGS=1` overrides for piping into log shippers

    Args:
        app_name: identifier baked into log records.
        use_stderr: route logs to stderr instead of stdout. **Required for
            MCP servers** — they use stdout for JSON-RPC protocol and any
            non-JSON byte corrupts the channel. Pass `True` from
            `mcp/noctusai/server.py`; leave `False` for `cli.py`.

    Idempotent: safe to call multiple times.
    """
    debug_env = os.environ.get("NOCTUSAI_DEBUG", "").strip().lower()
    debug = debug_env in {"1", "true", "yes", "on"}
    json_env = os.environ.get("NOCTUSAI_JSON_LOGS", "").strip().lower()
    if json_env in {"1", "true", "yes", "on"}:
        json_logs = True
    elif json_env in {"0", "false", "no", "off"}:
        json_logs = False
    else:
        # CLI default: human-readable. Backend prod default (JSON) doesn't
        # apply because CLI output is read directly by humans.
        json_logs = False
    stream = sys.stderr if use_stderr else None
    configure_logging(debug=debug, json_logs=json_logs, app_name=app_name, stream=stream)
