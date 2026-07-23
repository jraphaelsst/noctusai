"""Money coercion for the Meta Ads console — the two DISTINCT unit
conventions the Marketing API mixes on one integration, made explicit
so a future reader doesn't "fix" one into the other.

1. ``AdAccount.amount_spent`` / ``.balance`` / ``.spend_cap`` (and
   ``AdSet.daily_budget``) arrive from Graph ALREADY in the account's
   MINOR currency unit (cents for BRL) — Meta's Marketing API documents
   account/budget fields this way. The seed's ``AdAccount`` docstring
   confirms this: the values are kept as raw decimal strings rather
   than coerced, precisely because they're already minor-unit.
   :func:`cents_from_minor_unit_string` therefore just parses to int —
   NO ``* 100`` multiply.

2. ``AdInsightsRow.metrics["spend"/"cpc"/"cpm"]`` (Insights fields) are
   the OPPOSITE: Graph returns these in the account's MAJOR currency
   unit (e.g. ``spend="380.50"`` means R$380,50), and the seed mapper's
   generic flatten (``float(val)``) leaves them as a Python float in
   that same major unit. :func:`cents_from_major_unit_float` performs
   the ``* 100`` conversion this module is named for.

Both directions are genuine Marketing-API inconsistencies (not a bug in
either the seed adapter or this module) — see roadmap
``project-history/roadmaps/meta-ads-console-2026-07.md`` and
``KB § INTEGRATIONS/meta.md``. Every DB write in ``ads_sync_service``
and every live-read mapping in ``routers/ads_router`` goes through this
module so the two conventions are never silently conflated.
"""
from __future__ import annotations

from typing import Any


def cents_from_minor_unit_string(value: str | None) -> int | None:
    """``AdAccount``/``AdSet`` money fields — already minor-unit (cents).

    ``None``/empty/unparseable → ``None`` (never a silent 0 — a missing
    budget or balance is NULL, not zero)."""
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def cents_from_major_unit_float(value: Any) -> int | None:
    """``AdInsightsRow.metrics`` money fields (``spend``/``cpc``/``cpm``)
    — major-unit floats needing the ``* 100`` conversion to cents.

    ``None``/unparseable → ``None`` (e.g. ``cpc``/``cpm`` are undefined
    when clicks/impressions are zero for the row — never faked to 0)."""
    if value is None:
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    """Best-effort int coercion for count metrics (impressions/reach/
    clicks) — ``None``/unparseable → ``None``, never a silent 0."""
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


__all__ = [
    "cents_from_minor_unit_string",
    "cents_from_major_unit_float",
    "safe_int",
]
