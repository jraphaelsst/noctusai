"""Routing adapter contract.

Ported verbatim from
``whatsapp-google-scheduling/app/services/routing/types.py``.
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
    def travel_estimate(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> TravelEstimate: ...
