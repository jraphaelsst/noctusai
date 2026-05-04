"""Condominium-aware travel-minutes lookup wrapping the seed routing adapter.

The seed `RoutingAdapter` works in `Coordinates`; the scheduling engine works
in `location_id`. This module owns the `condo_id → Coordinates` mapping
(consumer-side, per `KB § PATTERNS/scheduling-seed.md`) and delegates the
minutes math to the seed adapter.

Cache shape:
- Per-instance `condo_id → Coordinates | None` (avoids re-querying Supabase
  for each `travel_minutes` call within one scheduling pass).
- Persistent `media_scheduling.route_groups` entries are NOT used as a
  travel-time cache today — `route_groups` is the same-day route plan,
  not a generic origin/dest cache. A persistent cache would need its
  own table; surfaced as an Improvement (see PROJECT.md §11 Phase 4).

When coordinates are missing on either condominium, returns
`fallback_minutes_when_coords_missing` (default 30) — the same conservative
fallback the source repo uses (`condominium_travel_service.py` line 26).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from noctusai_lib.integrations.google_maps import (
    Coordinates,
    RoutingAdapter,
    get_routing_adapter,
)

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)

DEFAULT_FALLBACK_MINUTES = 30


class RoutingLookup:
    """Condo-id-keyed travel-minutes lookup. Satisfies seed `TravelLookup`
    Protocol once wrapped in the adapter (see `scheduling_adapters.py`).

    Lazily fetches condo coordinates from `media_scheduling.condominiums`.
    Caches per-instance — fresh `RoutingLookup` per scheduling pass keeps
    the data fresh (consumer chooses cache lifetime).
    """

    def __init__(
        self,
        supabase: "Client",
        adapter: RoutingAdapter | None = None,
        fallback_minutes_when_coords_missing: int = DEFAULT_FALLBACK_MINUTES,
    ):
        self._sb = supabase
        self._adapter = adapter if adapter is not None else get_routing_adapter()
        self._fallback_minutes = fallback_minutes_when_coords_missing
        self._coord_cache: dict[int, Coordinates | None] = {}

    def travel_minutes(
        self,
        origin_condo_id: int,
        dest_condo_id: int,
    ) -> int:
        """Travel time in minutes between two condominiums.

        Same-id pair → 0 (preserves source contract; the seed
        `DefaultConflict` and `DefaultScorer` rely on this convention to
        skip transition buffers within a single locality).
        """
        if origin_condo_id == dest_condo_id:
            return 0
        origin = self._coords(origin_condo_id)
        destination = self._coords(dest_condo_id)
        if origin is None or destination is None:
            return self._fallback_minutes
        try:
            estimate = self._adapter.travel_estimate(origin, destination)
        except Exception:
            # Best-effort — if the routing API fails, log + fall back to
            # the conservative default so scheduling still proceeds.
            logger.warning(
                "Routing adapter failed for (%s -> %s); using fallback",
                origin_condo_id,
                dest_condo_id,
                exc_info=True,
            )
            return self._fallback_minutes
        return estimate.minutes

    def _coords(self, condo_id: int) -> Coordinates | None:
        if condo_id in self._coord_cache:
            return self._coord_cache[condo_id]
        try:
            response = (
                self._sb.schema("media_scheduling")
                .table("condominiums")
                .select("latitude, longitude")
                .eq("id", condo_id)
                .single()
                .execute()
            )
        except Exception:
            logger.warning(
                "Failed to fetch coordinates for condo %s", condo_id, exc_info=True
            )
            self._coord_cache[condo_id] = None
            return None

        row = response.data if response is not None else None
        coords: Coordinates | None
        if (
            row
            and row.get("latitude") is not None
            and row.get("longitude") is not None
        ):
            coords = Coordinates(
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
            )
        else:
            coords = None
        self._coord_cache[condo_id] = coords
        return coords


def make_routing_lookup(
    supabase: "Client",
    google_maps_api_key: str | None = None,
    fallback_minutes_when_coords_missing: int = DEFAULT_FALLBACK_MINUTES,
) -> RoutingLookup:
    """Compose a `RoutingLookup` against the live Maps adapter (or static
    fallback when `google_maps_api_key` is empty)."""
    adapter = get_routing_adapter(api_key=google_maps_api_key)
    return RoutingLookup(
        supabase=supabase,
        adapter=adapter,
        fallback_minutes_when_coords_missing=fallback_minutes_when_coords_missing,
    )
