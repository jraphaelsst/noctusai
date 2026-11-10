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
    factory = logging.getLogRecordFactory()
    logger_class = logging.getLoggerClass()
    named = {n: (logging.getLogger(n).level, logging.getLogger(n).filters[:])
             for n in ("uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "httpcore", "hpack")}
    yield
    logging.setLogRecordFactory(factory)
    logging.setLoggerClass(logger_class)
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


def test_extras_and_a_handler_added_before_configure_logging_see_a_clean_record():
    """The record factory scrubs at CREATION: `extra=` fields, and a handler/filter that reads the record before any
    logger-level filter ran, no longer see a phone."""
    seen: list[logging.LogRecord] = []

    class Spy(logging.Handler):
        def emit(self, record):
            seen.append(record)

    _run(False)
    spy = Spy()
    lg = logging.getLogger("app.spy")
    lg.addHandler(spy)
    try:
        lg.warning("to %s", "5511999990001", extra={"chat": "5511999990001@c.us", "nested": {"p": ["5511999990002"]}})
    finally:
        lg.removeHandler(spy)
    rec = seen[0]
    blob = repr((rec.msg, rec.args, rec.chat, rec.nested, rec.getMessage()))  # not `created` (a 10-digit float)
    assert not re.search(r"\d{8,}", blob), blob
    assert rec.chat == "…0001@c.us" and rec.nested == {"p": ["…0002"]}


def test_sentry_breadcrumbs_and_event_text_are_scrubbed():
    from noctusai_lib.api.sentry_scrub import scrub_event

    ev = scrub_event({
        "message": "send to 5511999990001",
        "logentry": {"message": "m %s", "formatted": "m 5511999990001"},
        "exception": {"values": [{"value": "GET /x?phone=5511999990001"}]},
        "breadcrumbs": {"values": [{"message": "check-exists 5511999990001"}]},
    })
    assert not re.search(r"\d{8,}", repr(ev)), ev


def test_only_exact_uuids_and_long_hex_tokens_are_exempt_every_other_digit_run_is_scrubbed():
    from noctusai_lib.log_scrub import scrub_digits

    for keep in ("00000000-0000-4000-8000-00000000a002", "48ab962b-ec86-517e-9e42-7b581f622377",
                 "00000000-1111-2222-3333-444455556666", "d41d8cd98f00b204e9800998ecf8427e",
                 "x=3EB0AB12-0000-4000-8000-123456789012"):
        assert scrub_digits(keep) == keep, keep
    for phone, expect in (
        ("5511999990001@c.us", "…0001@c.us"), ("phone=5511999990001&x=1", "phone=…0001&x=1"),
        ("+5511999990001", "+…0001"), ("true_5511999990001@c.us_3EB0AB", "true_…0001@c.us_3EB0AB"),
        ("to 5511999990001.", "to …0001."),
        # the three escapes the previous lookaround rule missed:
        ("5511999990001-1600000000@g.us", "…0001-…0000@g.us"),
        ("tel5511999990001", "tel…0001"),
        ("id=x5511999990001", "id=x…0001"),
        ("3EB0123456789ABC", "3EB…6789ABC"),  # a short hex-ish token: readability loses, nothing leaks
    ):
        assert scrub_digits(phone) == expect, phone


def test_the_formatter_scrubs_extras_even_when_the_record_never_went_through_the_creation_hooks():
    """A custom logger class / a logger made before configure_logging / a non-chaining factory: the formatter is the
    last stop and must still scrub message, args and `extra=` fields."""
    from noctusai_lib.logging_config import _JSONFormatter

    rec = logging.LogRecord("x", logging.WARNING, __file__, 1, "to %s", ("5511999990001",), None)
    rec.__dict__["chat"] = "5511999990001@c.us"   # an extra attached by a plain Logger that nobody re-classed
    import json

    data = json.loads(_JSONFormatter(app_name="t").format(rec))   # decoded: the raw text escapes the ellipsis as \u2026
    assert data["chat"] == "…0001@c.us" and data["message"] == "to …0001", data
