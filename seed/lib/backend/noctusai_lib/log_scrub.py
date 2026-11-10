"""Phone-number scrubbing for log lines: ONE implementation, installed on the ROOT handler by `configure_logging` (so the
products' own loggers, httpx and uvicorn request lines such as `?phone=<digits>` are covered) and on module loggers.

A run of 8+ digits in a log line is a phone number (or an id that embeds one): ``5511999990001`` -> ``…0001``.
Depth: KB § CONTEXT/INTEGRATIONS/whatsapp.md § 6a. Mask at the call site as well (`mask_chat_id`): the filter is the
safety net, not the plan.
"""
from __future__ import annotations

import logging
import re
import traceback
from typing import Any

#: 8+ digits NOT glued to a letter, digit or hyphen: a UUID (`00000000-0000-4000-...`) and any hex token keep their digit
#: runs (a bare lookahead would mangle ~5% of UUIDs), while `5511...@c.us`, `phone=5511...` and `true_5511...@c.us_ABC` are caught.
_DIGIT_RUN = re.compile(r"(?<![0-9A-Za-z-])\d{8,}(?![0-9A-Za-z-])")


def scrub_digits(text: Any) -> str:
    return _DIGIT_RUN.sub(lambda m: "…" + m.group()[-4:], str(text))


class PhoneScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = scrub_digits(record.getMessage())
            record.args = ()
            if record.exc_info:
                # KEEP exc_info (caplog, Sentry and tests read it) but pre-render a SCRUBBED text: any standard formatter
                # uses `record.exc_text` when set. The project's own formatters re-render from exc_info and scrub in
                # `formatException` (logging_config).
                record.exc_text = scrub_digits("".join(traceback.format_exception(*record.exc_info))).rstrip()
            elif record.exc_text:
                record.exc_text = scrub_digits(record.exc_text)
        except Exception:  # noqa: BLE001 - a logging filter must never break the call it observes
            record.msg, record.args = "<log line withheld: could not be scrubbed>", ()
        return True


def install_phone_scrub(target: "logging.Logger | logging.Handler") -> Any:
    if not any(isinstance(f, PhoneScrubFilter) for f in target.filters):
        target.addFilter(PhoneScrubFilter())
    return target


# --- record factory: scrub at CREATION, so every handler / filter / Sentry hook sees a clean record -------------------
_STD_ATTRS = frozenset(logging.LogRecord("x", 0, "x", 0, "x", None, None).__dict__) | {"message", "asctime", "taskName"}


def _scrub_obj(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return scrub_digits(value)
    if depth > 4:
        return value
    if isinstance(value, dict):
        return {k: _scrub_obj(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return type(value)(_scrub_obj(v, depth + 1) for v in value)
    return value


def scrub_record(record: logging.LogRecord) -> logging.LogRecord:
    """Scrub message, args, traceback text AND every `extra=` field of one record (a filter on a logger/handler misses extras
    and anything that looks at the record before the filter runs)."""
    PhoneScrubFilter().filter(record)
    for key in list(record.__dict__):
        if key not in _STD_ATTRS:
            record.__dict__[key] = _scrub_obj(record.__dict__[key])
    return record


class _ScrubLoggerMixin:
    def makeRecord(self, *args: Any, **kwargs: Any) -> logging.LogRecord:  # noqa: N802 - stdlib name
        # `extra=` fields are attached HERE, after the record factory ran: this is the only place that sees them first.
        return scrub_record(super().makeRecord(*args, **kwargs))  # type: ignore[misc]


class ScrubLogger(_ScrubLoggerMixin, logging.Logger):
    pass


class ScrubRootLogger(_ScrubLoggerMixin, logging.RootLogger):
    pass


def install_record_factory() -> None:
    """Idempotent. (1) the record factory scrubs message/args/traceback at creation; (2) `ScrubLogger` scrubs `extra=`
    fields (attached after the factory) for every logger created from now on, and existing plain loggers are re-classed,
    so every handler, filter and Sentry hook downstream sees a clean record."""
    current = logging.getLogRecordFactory()
    if not getattr(current, "_phone_scrub", False):
        def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            return scrub_record(current(*args, **kwargs))

        factory._phone_scrub = True  # type: ignore[attr-defined]
        logging.setLogRecordFactory(factory)
    logging.setLoggerClass(ScrubLogger)
    root = logging.getLogger()
    if type(root) is logging.RootLogger:
        root.__class__ = ScrubRootLogger
    for lg in list(logging.Logger.manager.loggerDict.values()):
        if type(lg) is logging.Logger:
            lg.__class__ = ScrubLogger


class ScrubbingFormatterMixin:
    """For formatters that render the traceback from ``exc_info`` themselves (the project's JSON/human formatters)."""

    def formatException(self, ei: Any) -> str:  # noqa: N802 - stdlib name
        return scrub_digits(super().formatException(ei))  # type: ignore[misc]
