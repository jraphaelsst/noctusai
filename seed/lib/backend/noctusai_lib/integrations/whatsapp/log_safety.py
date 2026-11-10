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

from typing import Any

from noctusai_lib.log_scrub import PhoneScrubFilter, install_phone_scrub, scrub_digits

__all__ = ["PhoneScrubFilter", "install_phone_scrub", "mask_chat_id", "scrub_digits"]


def mask_chat_id(value: Any) -> str:
    """``<digits>@suffix`` -> ``…<last4>@suffix``; anything without a long digit run is returned unchanged."""
    return scrub_digits(str(value if value is not None else ""))
