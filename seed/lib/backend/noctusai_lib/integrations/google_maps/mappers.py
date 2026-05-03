"""Pure-function translators for Google Routes API v2 wire shapes.

Ported verbatim from
`whatsapp-google-scheduling/app/services/routing/mappers.py` 2026-05-03
via `projects/whatsapp-seed-absorption/` Phase 8.
"""

from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.google_maps.types import Coordinates, TravelEstimate


def build_routes_request(origin: Coordinates, destination: Coordinates) -> dict[str, Any]:
    return {
        "origin": {
            "location": {
                "latLng": {"latitude": origin.latitude, "longitude": origin.longitude}
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": destination.latitude,
                    "longitude": destination.longitude,
                }
            }
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
    }


def parse_routes_response(response: dict[str, Any]) -> TravelEstimate:
    routes = response.get("routes") or []
    if not routes:
        return TravelEstimate(minutes=0, raw=response)

    first = routes[0]
    duration = first.get("duration", "0s")
    seconds = _parse_duration_seconds(duration)
    minutes = (seconds + 59) // 60
    distance = first.get("distanceMeters")
    return TravelEstimate(
        minutes=minutes,
        distance_meters=distance if isinstance(distance, int) else None,
        raw=first,
    )


def _parse_duration_seconds(value: str) -> int:
    if not isinstance(value, str):
        return 0
    text = value.strip()
    if text.endswith("s"):
        text = text[:-1]
    try:
        return int(float(text))
    except ValueError:
        return 0
