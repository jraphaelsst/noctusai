"""Static (deterministic) routing adapter.

Ported verbatim from
``whatsapp-google-scheduling/app/services/routing/static_adapter.py``.
"""
from __future__ import annotations

from app.services.routing.types import Coordinates, TravelEstimate


class StaticRoutingAdapter:
    """Deterministic routing adapter for tests + the no-API-key fallback.

    Returns a fixed travel time for any pair of distinct coordinates and
    0 minutes for identical coordinates. Real-world callers should use
    :class:`GoogleMapsRoutingAdapter`.
    """

    def __init__(self, default_minutes: int = 20):
        self.default_minutes = default_minutes

    def travel_estimate(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> TravelEstimate:
        if origin == destination:
            return TravelEstimate(minutes=0)
        return TravelEstimate(minutes=self.default_minutes)
