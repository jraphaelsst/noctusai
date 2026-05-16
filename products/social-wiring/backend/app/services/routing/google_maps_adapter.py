"""Google Maps Routes API v2 adapter.

Ported from
``whatsapp-google-scheduling/app/services/routing/google_maps_adapter.py``.

Reference: https://developers.google.com/maps/documentation/routes/overview

Uses an API key passed as the ``X-Goog-Api-Key`` header. The response
field mask is set to the minimum needed (``routes.duration`` and
``routes.distanceMeters``) so we don't get billed for unnecessary fields.

Per the reference repo's MVP, this does not request traffic-aware
estimates (``routingPreference: TRAFFIC_UNAWARE``). Switch to
``TRAFFIC_AWARE`` if/when the One Consultoria flow needs it.
"""
from __future__ import annotations

import httpx

from app.services.routing.mappers import build_routes_request, parse_routes_response
from app.services.routing.types import Coordinates, TravelEstimate


class GoogleMapsRoutingAdapter:
    BASE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
    FIELD_MASK = "routes.duration,routes.distanceMeters"

    def __init__(self, api_key: str, http_client: httpx.Client | None = None):
        self._api_key = api_key
        self._http_client = http_client

    def travel_estimate(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> TravelEstimate:
        body = build_routes_request(origin, destination)
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": self.FIELD_MASK,
        }
        client = self._http_client or httpx.Client(timeout=15)
        try:
            response = client.post(self.BASE_URL, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
        finally:
            if self._http_client is None:
                client.close()
        return parse_routes_response(data)
