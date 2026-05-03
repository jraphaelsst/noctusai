"""``google.maps.*`` — Google Maps routing tools.

Tools:
  - ``google.maps.travel_estimate``

Wraps ``noctusai_lib.integrations.google_maps.RoutingAdapter``.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool under ``google.maps.*``."""
    from . import travel_estimate

    travel_estimate.register(server)


__all__ = ["register_all"]
