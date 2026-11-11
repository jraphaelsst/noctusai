"""Honeypot field for public forms -- the cheap bot check (owner decision 2026-11-10, orbity lead capture).

A public form (lead capture, newsletter) renders ONE extra input that a human never sees and never fills; a bot that fills
every field does. The server treats a non-empty honeypot as a bot: it discards the submission QUIETLY (the caller gets the
same success shape as a real one, so the bot learns nothing), writes nothing, fires nothing, and records one no-PII event.

* :data:`HONEYPOT_FIELD` -- the one field name (not a real lead field, not ``email`` / ``website`` style names that
  browser autofill fills for a human).
* :func:`honeypot_tripped` -- the server-side test on the submitted body.
* :func:`honeypot_input_html` -- the markup the embed form renders: OFF-SCREEN (not ``type=hidden`` and not
  ``display:none``, both of which bots skip), ``autocomplete=off``, ``tabindex=-1``, ``aria-hidden`` so assistive tech and
  keyboard users never reach it. Single source of truth: forms copy this, tests pin it.
"""
from __future__ import annotations

from html import escape
from typing import Any, Mapping

HONEYPOT_FIELD = "hp_website"


def honeypot_tripped(body: Mapping[str, Any] | None, field: str = HONEYPOT_FIELD) -> bool:
    """True when the submitted ``body`` carries a non-empty honeypot value (any non-blank scalar counts)."""
    if not body:
        return False
    value = body.get(field)
    if value is None or value is False:
        return False
    return bool(str(value).strip())


def honeypot_input_html(field: str = HONEYPOT_FIELD) -> str:
    """The invisible input for the embed form (see the module docstring for why each attribute is there)."""
    name = escape(field, quote=True)
    return (
        f'<div style="position:absolute;left:-10000px;top:auto;width:1px;height:1px;overflow:hidden" aria-hidden="true">'
        f'<input type="text" name="{name}" id="{name}" value="" autocomplete="off" tabindex="-1" aria-hidden="true">'
        f"</div>"
    )


__all__ = ["HONEYPOT_FIELD", "honeypot_input_html", "honeypot_tripped"]
