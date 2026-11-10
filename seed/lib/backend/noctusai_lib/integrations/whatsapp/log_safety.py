"""No phone numbers in logs: ONE masking helper + a logging filter for every WhatsApp module logger.

A WAHA chat id is ``<digits>@c.us`` (the phone IS the id), a lid is ``<digits>@lid``, and an httpx error string embeds
the request URL (``/api/contacts/check-exists?phone=<digits>``). Any of them in a log line is a phone number in the log.

* :func:`mask_chat_id` -- ``5511999990001@c.us`` -> ``…0001@c.us`` (last 4 digits + the suffix).
* :func:`scrub_digits` -- any run of 8+ digits inside free text -> ``…<last4>``.
* :func:`install_phone_scrub` -- attach :class:`PhoneScrubFilter` to a module logger so message, args and traceback are
  scrubbed even where a call site forgot (defence in depth; call sites still mask explicitly).

NOC-REMEDIATE[phone-in-log-keeper]: no keeper bans an unmasked chat_id/phone/jid/lid argument in a `logger.*` call yet;
it belongs in mcp/noctusai/tools/noctus/dev/compliance.py as a warn-first shadow gate (AST over seed + active products'
backend, escape `# noc-allow: phone-in-log -- <reason>`), declared in the gate inventory with this module as its
construction leg. — 2026-11-10
"""
from __future__ import annotations

import logging
import re
import traceback
from typing import Any

_DIGIT_RUN = re.compile(r"\d{8,}")


def mask_chat_id(value: Any) -> str:
    """``<digits>@suffix`` -> ``…<last4>@suffix``; anything without a long digit run is returned unchanged."""
    return scrub_digits(str(value if value is not None else ""))


def scrub_digits(text: Any) -> str:
    return _DIGIT_RUN.sub(lambda m: "…" + m.group()[-4:], str(text))


class PhoneScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = scrub_digits(record.getMessage())
            record.args = ()
            if record.exc_info:
                record.exc_text = scrub_digits("".join(traceback.format_exception(*record.exc_info)))
                record.exc_info = None
            elif record.exc_text:
                record.exc_text = scrub_digits(record.exc_text)
        except Exception:  # noqa: BLE001 - a logging filter must never break the call it observes
            record.msg, record.args = "<log line withheld: could not be scrubbed>", ()
        return True


def install_phone_scrub(logger: logging.Logger) -> logging.Logger:
    if not any(isinstance(f, PhoneScrubFilter) for f in logger.filters):
        logger.addFilter(PhoneScrubFilter())
    return logger
