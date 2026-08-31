"""Lead-count extraction for the Meta Ads console — Meta's Marketing API
reports lead-gen conversions under TWO distinct ``action_type`` keys
depending on how the lead was captured, and this module is the ONE place
that reconciles them so every reader (compare/account/campaign-latest/
export) agrees on what "leads" means for a row — mirroring
``app.modules.meta_ads.services.money`` as the precedent for a small
shared helper in this module.

``actions["lead"]`` is the OFF-Facebook mechanism — Meta Pixel /
Conversions API firing the standard "Lead" event on the advertiser's own
website. ``actions["onsite_conversion.lead"]`` is the ON-Facebook/
Instagram mechanism — a native Instant Form submission (Lead Ads). These
are DISTINCT capture channels, not two labels on the same physical event:
a campaign configured with "Website + Instant forms" as its conversion
locations (a real, documented Meta objective) can report BOTH action
types on the SAME insights row, each counting leads collected through its
own channel. Meta's ``action_type`` breakdown never double-tags a single
lead under two types, so **summing** both keys is the honest total — a
``??`` first-match would silently drop the second channel's leads
whenever an account (or campaign) uses more than one. The pilot ad
account happens to populate only ``onsite_conversion.lead`` today, which
is exactly why summing and ``??``-ing agree for it and the backend gap
(the frontend's ``rowLeads`` already handles both keys) went unnoticed
for the other endpoints.

:func:`leads_from_actions` returns ``None`` (not ``0.0``) when the row's
``actions`` carries NEITHER key — preserving the "no lead data on this
row" signal callers like the campaign-latest tile render as "—" rather
than a fabricated zero (``KB`` no-silent-errors: a missing value is
``None``, never invented as 0). Callers aggregating leads ACROSS rows
(period totals) coerce that ``None`` to a zero CONTRIBUTION to the
running sum via ``leads_from_actions(...) or 0.0`` — correct, because a
row with no lead actions contributes nothing to the total; it just isn't
itself independently "zero leads" in the single-row UI sense.
"""
from __future__ import annotations

from typing import Any

_LEAD_ACTION_KEYS = ("lead", "onsite_conversion.lead")


def leads_from_actions(actions: dict[str, Any] | None) -> float | None:
    """Sum every known lead-action key present in ``actions``.

    ``None``/empty/neither key present → ``None`` (no lead data on this
    row — see module docstring, never a silent 0). A present key whose
    value doesn't parse as a number is skipped rather than crashing the
    aggregate."""
    if not actions:
        return None
    total = 0.0
    seen = False
    for key in _LEAD_ACTION_KEYS:
        if key not in actions:
            continue
        try:
            total += float(actions[key])
            seen = True
        except (TypeError, ValueError):
            continue
    return total if seen else None


__all__ = ["leads_from_actions"]
