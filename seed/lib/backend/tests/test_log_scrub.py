"""configure_logging installs the phone scrub on the ROOT handler and on uvicorn/httpx: no run of 8+ digits survives."""
from __future__ import annotations

import io
import logging
import re

import pytest

from noctusai_lib.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _restore_global_logging():
    """configure_logging REPLACES the root handlers and touches third-party loggers: put every one back so this module
    cannot starve a later test's caplog."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    named = {n: (logging.getLogger(n).level, logging.getLogger(n).filters[:])
             for n in ("uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "httpcore", "hpack")}
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    for n, (lvl, filters) in named.items():
        lg = logging.getLogger(n)
        lg.setLevel(lvl)
        lg.filters[:] = filters


def _run(json_logs: bool):
    stream = io.StringIO()
    configure_logging(debug=True, json_logs=json_logs, app_name="t", stream=stream)
    return stream


def test_a_uvicorn_access_line_with_a_phone_in_the_query_is_scrubbed():
    stream = _run(False)
    # uvicorn's own access logger shape: '%s - "%s %s HTTP/%s" %d'
    logging.getLogger("uvicorn.access").warning(
        '%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", "/api/contacts/check-exists?phone=5511999990001", "1.1", 200)
    out = stream.getvalue()
    assert "check-exists?phone=…0001" in out and not re.search(r"\d{8,}", out), out


def test_a_product_logger_and_httpx_and_tracebacks_are_scrubbed_in_both_formats():
    for json_logs in (False, True):
        stream = _run(json_logs)
        logging.getLogger("app.services.whatever").error("send to %s failed", "5511999990001@c.us")
        logging.getLogger("httpx").warning("HTTP Request: GET http://w/api/x?phone=5511999990002 \"HTTP/1.1 503\"")
        try:
            raise ValueError("boom 5511999990003")
        except ValueError:
            logging.getLogger("app.x").exception("handler failed")
        out = stream.getvalue()
        if json_logs:  # judge the DECODED values: the raw JSON text escapes the ellipsis as `\u2026`, which abuts the digits
            import json

            out = "\n".join(" ".join(str(v) for v in json.loads(line).values()) for line in out.splitlines() if line)
        assert "0001@c.us" in out and "0002" in out and "boom" in out and "0003" in out and "Traceback" in out
        assert not re.search(r"\d{8,}", out), (json_logs, out)
