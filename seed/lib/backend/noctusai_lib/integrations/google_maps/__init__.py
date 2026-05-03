"""Google Maps routing adapter — Routes API v2 + Static fallback.

Lifted 2026-05-03 by `projects/whatsapp-seed-absorption/` Phase 8 from
`whatsapp-google-scheduling/app/services/routing/`.

Public surface:
- `Coordinates`, `TravelEstimate`, `RoutingAdapter` Protocol.
- `StaticRoutingAdapter` — deterministic dev/test fallback.
- `GoogleMapsRoutingAdapter` — live Maps API; takes an API key.
- `get_routing_adapter(api_key=)` factory.
- Pure-function mappers (`build_routes_request`, `parse_routes_response`).

To plug into `noctusai_lib.domain.scheduling.SchedulingEngine`, build a
`TravelLookup` that owns a location_id → Coordinates mapping and
delegates `travel_minutes(...)` to `RoutingAdapter.travel_estimate(...)`.
The mapping is product-specific (real-estate condos, therapy clinic
rooms), so it stays consumer-side.
"""

from noctusai_lib.integrations.google_maps.google_maps_adapter import (
    GoogleMapsRoutingAdapter,
)
from noctusai_lib.integrations.google_maps.mappers import (
    build_routes_request,
    parse_routes_response,
)
from noctusai_lib.integrations.google_maps.static_adapter import StaticRoutingAdapter
from noctusai_lib.integrations.google_maps.types import (
    Coordinates,
    RoutingAdapter,
    TravelEstimate,
)


def get_routing_adapter(api_key: str | None = None) -> RoutingAdapter:
    """Routes API → Static fallback. Returns `GoogleMapsRoutingAdapter`
    when `api_key` is set; otherwise `StaticRoutingAdapter`."""
    if api_key:
        return GoogleMapsRoutingAdapter(api_key)
    return StaticRoutingAdapter()


__all__ = [
    "Coordinates",
    "GoogleMapsRoutingAdapter",
    "RoutingAdapter",
    "StaticRoutingAdapter",
    "TravelEstimate",
    "build_routes_request",
    "get_routing_adapter",
    "parse_routes_response",
]
