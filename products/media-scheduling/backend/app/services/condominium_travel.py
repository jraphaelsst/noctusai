"""Same-condominium duration semantics — thin wrapper.

The seed `SchedulingRules.same_location_duration_minutes` already covers the
"two consecutive appointments at the same location pack to a shorter slot"
rule (verbatim port of the source's `same_condominium_duration_minutes`).
This module exists so the per-product knob lives in one place + so any
future override (e.g. condo-specific durations) plugs in without editing
the seed engine.

Source reference:
- `whatsapp-google-scheduling/app/services/scheduling_service.py:_duration_for`
- `whatsapp-google-scheduling/app/services/condominium_travel_service.py`
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from noctusai_lib.domain.scheduling import SchedulingRules

if TYPE_CHECKING:
    from supabase import Client


# Source defaults — preserved verbatim from
# `whatsapp-google-scheduling/app/services/scheduling_service.py:SchedulingRules`.
DEFAULT_STANDARD_DURATION_MINUTES = 90
DEFAULT_SAME_CONDOMINIUM_DURATION_MINUTES = 60
DEFAULT_TRANSITION_BUFFER_MINUTES = 10


def same_condominium_duration_minutes(
    supabase: "Client | None" = None,
    *,
    target_condo_id: int | None = None,
) -> int:
    """Returns the duration override when consecutive appointments are at
    the same condominium.

    Today this is a flat constant — the source repo does the same. The
    `supabase` + `target_condo_id` parameters are reserved for future
    per-condo override fetches (e.g. high-rise condos that need an extra
    pack-up slot). Pass `None` to get the default constant.
    """
    # TODO Phase 6+: per-condo override via media_scheduling.condominiums.notes
    # JSONB column or a dedicated condominium_overrides table.
    return DEFAULT_SAME_CONDOMINIUM_DURATION_MINUTES


def default_scheduling_rules(timezone_name: str) -> SchedulingRules:
    """Build a `SchedulingRules` matching the source repo's defaults.

    `timezone_name` is an IANA zone (e.g. ``"America/Sao_Paulo"``); this
    keeps the rules object timezone-aware for date arithmetic in the
    engine.
    """
    from zoneinfo import ZoneInfo

    return SchedulingRules(
        timezone=ZoneInfo(timezone_name),
        transition_buffer_minutes=DEFAULT_TRANSITION_BUFFER_MINUTES,
        default_duration_minutes=DEFAULT_STANDARD_DURATION_MINUTES,
        same_location_duration_minutes=DEFAULT_SAME_CONDOMINIUM_DURATION_MINUTES,
    )
