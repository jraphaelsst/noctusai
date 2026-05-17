"""Routing package factory.

Ported from
``whatsapp-google-scheduling/app/services/routing/__init__.py``.

Resolution:
- ``GOOGLE_MAPS_API_KEY`` set → :class:`GoogleMapsRoutingAdapter`
- otherwise                  → :class:`StaticRoutingAdapter`
"""
from __future__ import annotations

import logging

from app.config import settings as default_settings
from app.services.routing.google_maps_adapter import GoogleMapsRoutingAdapter
from app.services.routing.static_adapter import StaticRoutingAdapter
from app.services.routing.types import Coordinates, RoutingAdapter, TravelEstimate

logger = logging.getLogger(__name__)

__all__ = [
    "Coordinates",
    "GoogleMapsRoutingAdapter",
    "RoutingAdapter",
    "StaticRoutingAdapter",
    "TravelEstimate",
    "get_routing_adapter",
]


def get_routing_adapter(settings=None) -> RoutingAdapter:
    settings = settings or default_settings
    if settings.google_maps_api_key:
        logger.info("Routing adapter: GoogleMapsRoutingAdapter (Maps API key configured)")
        return GoogleMapsRoutingAdapter(settings.google_maps_api_key)
    return StaticRoutingAdapter()
