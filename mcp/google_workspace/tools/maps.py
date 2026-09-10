"""google.maps.* tools — thin wrapper over the seed routing adapter.

Tools registered:
- google.maps.travel_estimate — READ. Travel time between two coords.

The Routes-API call, the Static fallback, and the value objects all
ship in `noctusai_lib.integrations.google_maps`. This module composes
the factory (`get_routing_adapter(api_key=...)`): a Maps API key →
`GoogleMapsRoutingAdapter`, otherwise the deterministic
`StaticRoutingAdapter` (flat estimate — fine for dev/test).
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.google_maps import Coordinates, get_routing_adapter

from _kit.errors import typed_error

from settings import get_settings
from schemas import TravelEstimateInput, TravelEstimateOutput

logger = logging.getLogger(__name__)


async def travel_estimate(args: dict) -> dict:
    inp = TravelEstimateInput(**args)
    s = get_settings()
    adapter = get_routing_adapter(api_key=s.maps_api_key)
    kind = "google" if s.maps_api_key else "static"
    try:
        est = adapter.travel_estimate(
            Coordinates(inp.origin.latitude, inp.origin.longitude),
            Coordinates(inp.destination.latitude, inp.destination.longitude),
        )
    except Exception as e:  # noqa: BLE001
        return TravelEstimateOutput(
            minutes=0, distance_meters=None, adapter=kind
        ).model_dump() | {"error": typed_error(e)}
    return TravelEstimateOutput(
        minutes=est.minutes,
        distance_meters=est.distance_meters,
        adapter=kind,
    ).model_dump()


HANDLERS = {
    "google.maps.travel_estimate": travel_estimate,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="google.maps.travel_estimate",
            description=(
                "Estimate travel time (minutes) + distance between two "
                "lat/lng coordinates via the Google Routes API v2. "
                "Read-only. Falls back to a deterministic flat estimate "
                "(StaticRoutingAdapter, ~20min) when no Maps API key is "
                "configured — the `adapter` field reports which ran."
            ),
            inputSchema=TravelEstimateInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
