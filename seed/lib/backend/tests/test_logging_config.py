"""Tests for `noctusai_lib.logging_config`.

Covers:
- `configure_logging(...)` core API (level / formatter / handler shape)
- `auto_configure_for_cli(...)` env-driven CLI entry-point
- `use_stderr=True` path for MCP-server stdio protocol safety
"""
from __future__ import annotations

import io
import logging
import os
import sys
from unittest.mock import patch

import pytest

from noctusai_lib.logging_config import (
    auto_configure_for_cli,
    configure_logging,
    resolve_json_logs,
)


_THIRD_PARTY_LOGGERS = ("uvicorn.access", "httpx", "httpcore", "hpack")


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Save + restore root logger state AND the third-party loggers
    `configure_logging` mutates (`uvicorn.access`, `httpx`, `httpcore`,
    `hpack`). Without this, repeated test runs leak the WARNING-level
    setting onto those loggers and any later test that asserts on
    INFO-level httpx output sees pollution.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_third_party = {
        name: logging.getLogger(name).level
        for name in _THIRD_PARTY_LOGGERS
    }
    yield
    for h in root.handlers[:]:
        root.removeHandler(h)
    for h in saved_handlers:
        root.addHandler(h)
    root.setLevel(saved_level)
    for name, level in saved_third_party.items():
        logging.getLogger(name).setLevel(level)


class TestConfigureLogging:
    def test_debug_uses_human_readable_by_default(self):
        configure_logging(debug=True, json_logs=False)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        # Single handler installed by configure_logging.
        handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
        assert len(handlers) == 1
        # Formatter is the human-readable variant (has the timestamp | level | … shape).
        record = logging.LogRecord("t", logging.INFO, "p", 1, "hi", None, None)
        formatted = handlers[0].formatter.format(record)
        assert " | INFO" in formatted
        assert "hi" in formatted

    def test_json_logs_emit_json(self):
        configure_logging(debug=False, json_logs=True, app_name="my-app")
        root = logging.getLogger()
        h = next(h for h in root.handlers if isinstance(h, logging.StreamHandler))
        record = logging.LogRecord("t", logging.WARNING, "p", 1, "hello", None, None)
        formatted = h.formatter.format(record)
        import json as _json
        parsed = _json.loads(formatted)
        assert parsed["level"] == "WARNING"
        assert parsed["message"] == "hello"
        assert parsed["app"] == "my-app"
        assert "timestamp" in parsed

    def test_app_name_appears_in_human_readable_output(self):
        configure_logging(debug=True, json_logs=False, app_name="erp")
        root = logging.getLogger()
        h = next(h for h in root.handlers if isinstance(h, logging.StreamHandler))
        record = logging.LogRecord("t", logging.INFO, "p", 1, "hi", None, None)
        formatted = h.formatter.format(record)
        assert "[erp]" in formatted

    def test_third_party_loggers_silenced(self):
        configure_logging(debug=True)
        for name in ("uvicorn.access", "httpx", "httpcore", "hpack"):
            assert logging.getLogger(name).level == logging.WARNING

    def test_stream_override_routes_to_stderr(self):
        """`stream=sys.stderr` is required for MCP servers — stdout is JSON-RPC."""
        buf = io.StringIO()
        configure_logging(debug=True, json_logs=False, stream=buf)
        logging.getLogger("test").warning("captured")
        assert "captured" in buf.getvalue()

    def test_idempotent_does_not_leak_handlers(self):
        configure_logging(debug=True)
        first_count = len(logging.getLogger().handlers)
        configure_logging(debug=True)
        configure_logging(debug=True)
        # Same handler count after repeated calls.
        assert len(logging.getLogger().handlers) == first_count


class TestAutoConfigureForCli:
    def _capture(self) -> io.StringIO:
        return io.StringIO()

    def test_default_is_info_level_human_readable(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ("NOCTUSAI_DEBUG", "NOCTUSAI_JSON_LOGS"):
                os.environ.pop(k, None)
            auto_configure_for_cli("test-app")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_debug_env_var_enables_debug_level(self):
        with patch.dict(os.environ, {"NOCTUSAI_DEBUG": "1"}, clear=False):
            auto_configure_for_cli("test-app")
        assert logging.getLogger().level == logging.DEBUG

    def test_json_logs_env_var_overrides_format(self):
        with patch.dict(os.environ, {"NOCTUSAI_JSON_LOGS": "1"}, clear=False):
            auto_configure_for_cli("test-app")
        h = next(h for h in logging.getLogger().handlers if isinstance(h, logging.StreamHandler))
        # JSON formatter produces parsable JSON.
        record = logging.LogRecord("t", logging.INFO, "p", 1, "x", None, None)
        import json as _json
        _json.loads(h.formatter.format(record))  # raises if not JSON

    def test_use_stderr_routes_to_stderr(self):
        """MCP server safety check: when stdio is the protocol, logs must
        not pollute stdout.
        """
        with patch.dict(os.environ, {}, clear=False):
            auto_configure_for_cli("mcp-server", use_stderr=True)
        h = next(h for h in logging.getLogger().handlers if isinstance(h, logging.StreamHandler))
        assert h.stream is sys.stderr

    def test_use_stderr_default_false_routes_to_stdout(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ("NOCTUSAI_DEBUG", "NOCTUSAI_JSON_LOGS"):
                os.environ.pop(k, None)
            auto_configure_for_cli("cli")
        h = next(h for h in logging.getLogger().handlers if isinstance(h, logging.StreamHandler))
        assert h.stream is sys.stdout

    def test_truthy_env_values_recognized(self):
        for val in ("1", "true", "TRUE", "yes", "on"):
            with patch.dict(os.environ, {"NOCTUSAI_DEBUG": val}, clear=False):
                auto_configure_for_cli("test")
            assert logging.getLogger().level == logging.DEBUG, f"failed for {val!r}"

    def test_falsy_env_values_yield_info(self):
        for val in ("0", "false", "no", "off", ""):
            with patch.dict(os.environ, {"NOCTUSAI_DEBUG": val}, clear=False):
                auto_configure_for_cli("test")
            assert logging.getLogger().level == logging.INFO, f"failed for {val!r}"


class TestResolveJsonLogs:
    """Log FORMAT resolved independently of log LEVEL.

    These were one knob until 2026-08-24: the seed passed
    `json_logs=not settings.debug`, so wanting readable logs in production
    meant setting `DEBUG=true` — which also dropped the level to DEBUG and
    published `/docs` and `/openapi.json` to the public internet. Production
    ran that way. The `default` parameter is the whole point: UNSET must mean
    "caller decides", not "false".
    """

    def _clear(self):
        os.environ.pop("NOCTUSAI_JSON_LOGS", None)

    def test_unset_returns_the_callers_default_either_way(self):
        with patch.dict(os.environ, {}, clear=False):
            self._clear()
            assert resolve_json_logs(default=True) is True
            assert resolve_json_logs(default=False) is False

    def test_explicit_true_overrides_a_false_default(self):
        for val in ("1", "true", "TRUE", "yes", "on", " On "):
            with patch.dict(os.environ, {"NOCTUSAI_JSON_LOGS": val}, clear=False):
                assert resolve_json_logs(default=False) is True, f"failed for {val!r}"

    def test_explicit_false_overrides_a_true_default(self):
        """The case that matters in prod: readable logs WITHOUT setting DEBUG."""
        for val in ("0", "false", "no", "off", " OFF "):
            with patch.dict(os.environ, {"NOCTUSAI_JSON_LOGS": val}, clear=False):
                assert resolve_json_logs(default=True) is False, f"failed for {val!r}"

    def test_an_unrecognised_value_falls_back_to_the_default(self):
        """Not silently false — an unparseable value must not flip the shape."""
        with patch.dict(os.environ, {"NOCTUSAI_JSON_LOGS": "maybe"}, clear=False):
            assert resolve_json_logs(default=True) is True
            assert resolve_json_logs(default=False) is False

    def test_empty_string_is_treated_as_unset(self):
        with patch.dict(os.environ, {"NOCTUSAI_JSON_LOGS": ""}, clear=False):
            assert resolve_json_logs(default=True) is True
