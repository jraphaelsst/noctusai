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

_DIGIT_RUN = re.compile(r"\d{8,}")


def scrub_digits(text: Any) -> str:
    return _DIGIT_RUN.sub(lambda m: "…" + m.group()[-4:], str(text))


class PhoneScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = scrub_digits(record.getMessage())
            record.args = ()
            if record.exc_info:
                # Not every formatter honours exc_text (the project's own do not): fold the SCRUBBED traceback into the
                # message so it is neither lost nor leaked, and drop exc_info so nothing re-renders the raw one.
                tb = scrub_digits("".join(traceback.format_exception(*record.exc_info))).rstrip()
                record.msg = f"{record.msg}\n{tb}"
                record.exc_text = None
                record.exc_info = None
            elif record.exc_text:
                record.exc_text = scrub_digits(record.exc_text)
        except Exception:  # noqa: BLE001 - a logging filter must never break the call it observes
            record.msg, record.args = "<log line withheld: could not be scrubbed>", ()
        return True


def install_phone_scrub(target: "logging.Logger | logging.Handler") -> Any:
    if not any(isinstance(f, PhoneScrubFilter) for f in target.filters):
        target.addFilter(PhoneScrubFilter())
    return target
