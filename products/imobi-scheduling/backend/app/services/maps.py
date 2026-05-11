"""Google Maps routing wiring for the Imobi Scheduling bot — Phase 8.

**Why this module exists** — Phase 8 of `projects/imobi-scheduling-bot-creation/`
plugs the seed `noctusai_lib.integrations.google_maps` adapter into the
scheduling engine's `TravelLookup` Protocol seam. The seed ships:

  - `RoutingAdapter` Protocol (single method: ``travel_estimate(origin,
    destination) → TravelEstimate``).
  - `StaticRoutingAdapter` (dev/test deterministic).
  - `GoogleMapsRoutingAdapter` (live API).
  - `get_routing_adapter(api_key=)` factory.

The scheduling-engine wants a different shape — `TravelLookup` (single
method ``travel_minutes(origin_id, destination_id) → int`` keyed by
location-id strings). This module is the bridge: a small adapter that
owns a ``condominium_id → Coordinates`` map and delegates per pair to
the seed's `RoutingAdapter`.

**Verify-the-seed-ships-it test (2026-05-11).** Re-read the seed's
``noctusai_lib/integrations/google_maps/__init__.py`` + ``static_adapter.py``
+ ``google_maps_adapter.py``: Protocol+Fake+Real+factory ALL present. No
carve-out — consumer-side work here is just the location-id → coords
mapping bridge (which the seed's __init__ docstring explicitly says is
consumer-side because location-id semantics are product-specific).

**Travel-buffer composition** — note that the scheduling engine adds its
own ``transition_buffer_minutes`` on TOP of the travel minutes this
returns. The buffer is configured in ``settings.imobi_scheduling_travel_buffer_minutes``
(default 10 min) and applied by `DefaultConflict`. This module returns
RAW travel minutes only — don't double-count buffer here.

**Caching.** The ``routes`` table (migration 001) caches origin/destination
pairs. A future iteration may consult that cache before hitting the API;
today this module is a pass-through so the seed adapter handles
network calls directly. Tracked as P2 improvement.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from noctusai_lib.integrations.google_maps import (
    Coordinates,
    RoutingAdapter,
    StaticRoutingAdapter,
    get_routing_adapter,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GoogleMapsTravelLookup — bridges seed RoutingAdapter → engine TravelLookup
# ---------------------------------------------------------------------------


class GoogleMapsTravelLookup:
    """`TravelLookup` Protocol impl for `noctusai_lib.domain.scheduling`.

    The engine calls ``travel_minutes(origin_id, destination_id) → int``
    with location-id strings; this class owns the
    ``location_id → Coordinates`` mapping + delegates per pair to the
    seed's `RoutingAdapter`. The mapping is supplied at construction
    time by the consumer (Phase 8 ships the table fetched at startup;
    a future iteration can refresh on-demand).

    Returns ``0`` for same-location pairs (matches `StaticRoutingAdapter`
    semantics). Unknown location IDs return a conservative default
    (``default_minutes``, 0 by default) so the engine doesn't crash on
    a missing condominium row — the worst case is a too-optimistic gap
    estimate which `DefaultConflict.transition_buffer_minutes` cushions.
    """

    def __init__(
        self,
        adapter: RoutingAdapter,
        location_coords: dict[str, Coordinates],
        *,
        default_minutes: int = 0,
    ) -> None:
        self._adapter = adapter
        self._coords = dict(location_coords)
        self._default_minutes = int(default_minutes)

    def travel_minutes(
        self,
        origin_id: str,
        destination_id: str,
    ) -> int:
        """Return travel-minutes between two location IDs.

        Mirrors `noctusai_lib.domain.scheduling.TravelLookup.travel_minutes`.

        Behavior:
          - Same origin/destination → ``0``.
          - Both IDs known → seed adapter call → integer minutes.
          - Unknown ID → ``default_minutes`` + WARN log.
        """
        if origin_id == destination_id:
            return 0

        origin = self._coords.get(origin_id)
        destination = self._coords.get(destination_id)
        if origin is None or destination is None:
            logger.warning(
                "GoogleMapsTravelLookup missing coords: origin_id=%s known=%s "
                "destination_id=%s known=%s; returning default=%s",
                origin_id, origin is not None,
                destination_id, destination is not None,
                self._default_minutes,
            )
            return self._default_minutes

        estimate = self._adapter.travel_estimate(origin, destination)
        return int(estimate.minutes)

    def add_location(self, location_id: str, coords: Coordinates) -> None:
        """Register / replace a location → coords mapping.

        Used by Phase 9+ when condominiums are added at runtime; Phase 8
        loads the whole table once at startup so this is mostly a
        future-proofing hook today.
        """
        self._coords[location_id] = coords


# ---------------------------------------------------------------------------
# MapsModule — top-level wiring object
# ---------------------------------------------------------------------------


@dataclass
class MapsModule:
    """Wired routing adapter + travel-lookup.

    Attributes:
        adapter: Seed `RoutingAdapter` (Static fallback or live API).
        travel_lookup: The `GoogleMapsTravelLookup` consumed by the
            scheduling engine.
    """

    adapter: RoutingAdapter
    travel_lookup: GoogleMapsTravelLookup


# Module-level singleton populated by ``configure_maps_module(...)``.
_module: Optional[MapsModule] = None


def get_maps_module() -> MapsModule:
    """Return the configured `MapsModule`. Raises if not wired."""
    if _module is None:
        raise RuntimeError(
            "Maps module is not configured. "
            "Call `configure_maps_module(...)` from lifespan startup."
        )
    return _module


def configure_maps_module(
    *,
    api_key: Optional[str] = None,
    location_coords: Optional[dict[str, Coordinates]] = None,
    adapter: Optional[RoutingAdapter] = None,
    default_minutes: int = 0,
) -> MapsModule:
    """Build + cache the `MapsModule`.

    Two ways to wire:

      1. **Production path** — pass ``api_key``. Seed factory returns
         `GoogleMapsRoutingAdapter`. ``location_coords`` is the
         ``condominium_id → Coordinates`` map (fetched from the
         ``imobi_scheduling.condominiums`` table at startup).
      2. **Test path / dev path** — omit ``api_key`` → seed factory
         returns `StaticRoutingAdapter` (deterministic default 20-min
         travel). Or pass ``adapter=`` directly.

    Args:
        api_key: Google Maps API key.
        location_coords: Pre-built ``location_id → Coordinates`` map.
            Empty/None ships an empty mapping; consumers can populate
            via ``travel_lookup.add_location(...)``.
        adapter: Pre-built `RoutingAdapter` (test override).
        default_minutes: Fallback minutes when a location ID isn't in
            the coords map. Default ``0`` is conservative — biases the
            engine toward proposing earlier slots and lets
            `DefaultConflict`'s transition buffer absorb the error.

    Returns:
        The configured module (cached at module-level).
    """
    global _module

    if adapter is None:
        adapter = get_routing_adapter(api_key=api_key)

    travel_lookup = GoogleMapsTravelLookup(
        adapter=adapter,
        location_coords=location_coords or {},
        default_minutes=default_minutes,
    )
    _module = MapsModule(adapter=adapter, travel_lookup=travel_lookup)
    logger.info(
        "Maps module configured: adapter=%s locations_loaded=%d",
        type(adapter).__name__, len(travel_lookup._coords),
    )
    return _module


def _reset_for_tests() -> None:
    """Test helper — clears the module-level singleton."""
    global _module
    _module = None


# ---------------------------------------------------------------------------
# Coords loader — fetches condominium coordinates from the DB at startup
# ---------------------------------------------------------------------------


def load_condominium_coords(
    admin_client: Any,
    *,
    org_id: str,
) -> dict[str, Coordinates]:
    """Fetch ``condominium_id → Coordinates`` for an org.

    Reads the ``imobi_scheduling.condominiums`` table. Rows missing
    ``latitude`` or ``longitude`` are skipped with a WARN log
    (a future per-condo data-cleanup ticket should backfill).

    Returns:
        Dict mapping ``condominium_id`` (str) → `Coordinates`. Empty
        when the table has no usable rows.
    """
    try:
        response = (
            admin_client.schema("imobi_scheduling")
            .table("condominiums")
            .select("id, latitude, longitude")
            .eq("org_id", org_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 — startup load is best-effort.
        logger.warning(
            "Condominium coords load failed: org_id=%s err=%s",
            org_id, exc,
        )
        return {}

    rows = response.data or []
    coords: dict[str, Coordinates] = {}
    for row in rows:
        try:
            lat = row.get("latitude")
            lng = row.get("longitude")
            if lat is None or lng is None:
                logger.warning(
                    "Condominium row missing coords: id=%s — skipping.",
                    row.get("id"),
                )
                continue
            coords[str(row["id"])] = Coordinates(
                latitude=float(lat),
                longitude=float(lng),
            )
        except (TypeError, ValueError, KeyError) as exc:
            logger.warning(
                "Malformed condominium row: id=%s err=%s",
                row.get("id"), exc,
            )
            continue
    return coords


__all__ = [
    "GoogleMapsTravelLookup",
    "MapsModule",
    "configure_maps_module",
    "get_maps_module",
    "load_condominium_coords",
]
