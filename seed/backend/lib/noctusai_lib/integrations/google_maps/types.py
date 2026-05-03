"""Routing adapter value objects + Protocol.

Ported from
`whatsapp-google-scheduling/app/services/routing/types.py` 2026-05-03
via `projects/whatsapp-seed-absorption/` Phase 8.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class TravelEstimate:
    minutes: int
    distance_meters: int | None = None
    raw: dict[str, Any] | None = None


class RoutingAdapter(Protocol):
    """Travel-estimate contract between two coordinates. Implementations
    today: `StaticRoutingAdapter` (deterministic), `GoogleMapsRoutingAdapter`
    (Google Routes API v2).

    To plug into `noctusai_lib.domain.scheduling.SchedulingEngine`, build
    a `TravelLookup` that owns a location_id → Coordinates mapping and
    delegates to a `RoutingAdapter`. Sibling did this inline in
    `condominium_travel_service.py`; we keep it consumer-side because
    location-id semantics are product-specific."""

    def travel_estimate(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> TravelEstimate: ...
