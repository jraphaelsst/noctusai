"""Routing package — converged onto the seed.

Was a product-local port of
``whatsapp-google-scheduling/app/services/routing/`` (value objects +
both adapters byte-identical to `noctusai_lib.integrations.google_maps`).
Converged 2026-05-17 by `projects/seed-adapter-convergence/`: the value
objects, both adapters, and the factory now come from the seed. This
module keeps only the product-shaped factory wrapper
(`get_routing_adapter(settings=)`) that reads the product config — the
adapter classes are re-exported from the seed so consumer
`isinstance(adapter, GoogleMapsRoutingAdapter)` / `StaticRoutingAdapter`
checks remain transparent (same classes, not look-alikes).

The product-local `google_maps_adapter.py` / `static_adapter.py` /
`types.py` are retired — this is now a thin seed re-export shim.
"""
from __future__ import annotations

import logging

from noctusai_lib.integrations.google_maps import (
    Coordinates,
    GoogleMapsRoutingAdapter,
    RoutingAdapter,
    StaticRoutingAdapter,
    TravelEstimate,
)
from noctusai_lib.integrations.google_maps import (
    get_routing_adapter as _seed_get_routing_adapter,
)

from app.config import settings as default_settings

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
    """Product-shaped wrapper over the seed factory.

    Reads `google_maps_api_key` from the product settings and delegates
    to `noctusai_lib.integrations.google_maps.get_routing_adapter`
    (Maps key set → `GoogleMapsRoutingAdapter`; else
    `StaticRoutingAdapter`)."""
    settings = settings or default_settings
    return _seed_get_routing_adapter(settings.google_maps_api_key)
