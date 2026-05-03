"""Deterministic static-distance routing adapter (no network).

Ported verbatim from
`whatsapp-google-scheduling/app/services/routing/static_adapter.py`
2026-05-03 via `projects/whatsapp-seed-absorption/` Phase 8.

Use as the dev/local fallback when no Google Maps API key is configured,
or in tests as a deterministic stand-in.
"""

from __future__ import annotations

from noctusai_lib.integrations.google_maps.types import Coordinates, TravelEstimate


class StaticRoutingAdapter:
    """Returns `default_minutes` for any pair of distinct coordinates,
    `0` for identical coordinates."""

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
