"""Typed errors for the FX/PTAX integration.

🔴 There is an `LLM_USD_TO_BRL=5.0` env-var default in
`noctusai_lib.integrations.llm.budget` used to render a live cost
projection in a UI while an LLM call is in flight. That default MUST
NEVER be reached for from this module, or from any consumer of this
module, as a substitute for a real PTAX lookup on a `FxBulletinNotFoundError`.
The two numbers answer different questions: `LLM_USD_TO_BRL` is an
admin-tunable *estimate* for a number that has not happened yet;
`PtaxRate` is the *actual* published rate for a specific trading day,
used to permanently price a cost record that already happened. Silently
reaching for the estimate here would let a historical cost record
silently re-price itself in a way nobody could audit later. The correct
behaviour on `FxBulletinNotFoundError` is: catch it, mark the cost
record `fx_pending`, and backfill the real rate later (e.g. a retry
once BCB has published, or once the lookback window is widened).
"""

from __future__ import annotations

from datetime import date


class FxError(Exception):
    """Base for every FX/PTAX integration failure."""


class FxBulletinNotFoundError(FxError):
    """No BCB PTAX fechamento bulletin was published within the lookback
    window ending at `requested_date`.

    Raised — never silently defaulted to a fallback rate — so the
    consumer can mark the cost record `fx_pending` and backfill later.
    """

    def __init__(self, requested_date: date, lookback_days: int) -> None:
        message = (
            f"No PTAX fechamento bulletin published in the {lookback_days}-day "
            f"window ending {requested_date.isoformat()}"
        )
        super().__init__(message)
        self.requested_date = requested_date
        self.lookback_days = lookback_days


class FxUpstreamError(FxError):
    """BCB Olinda was unreachable, answered non-2xx, returned a non-JSON
    body, or returned a JSON shape `parse_ptax_response` could not read.

    Distinct from `FxBulletinNotFoundError`: this means "we don't know
    what BCB said" (transient — retry may help), not "BCB confirmed
    there is nothing here" (structural for that date until backfilled).
    """


__all__ = [
    "FxBulletinNotFoundError",
    "FxError",
    "FxUpstreamError",
]
