"""Product-side adapters plugging into the seed `SchedulingEngine`.

Per `KB § PATTERNS/scheduling-seed.md`, the engine is wired with three
Protocols (`Conflict` / `Scorer` / `TravelLookup`); product-specific
business logic lives in adapter implementations, not the seed.

For Media Scheduling the source-repo math (verbatim port at the seed
level) is sufficient — no real-estate-specific Conflict or Scorer
beyond what `DefaultConflict` + `DefaultScorer` already cover (they
were the source repo's `_is_valid` and `_score` lifted verbatim).

The one product-specific bit is the `TravelLookup` adapter that wraps
our condo-aware `RoutingLookup`. We keep `make_scheduling_engine`
factoring so future Conflict/Scorer extensions plug in without touching
caller code.
"""

from __future__ import annotations

from noctusai_lib.domain.scheduling import (
    Conflict,
    DefaultConflict,
    DefaultScorer,
    SchedulingEngine,
    SchedulingRules,
    Scorer,
    TravelLookup,
)

from app.services.routing_lookup import RoutingLookup


class CondoTravelLookup:
    """`TravelLookup` Protocol impl wrapping a `RoutingLookup`.

    Adapter exists to (a) make the seed-Protocol satisfaction explicit
    and (b) preserve generic `location_id` vocabulary at the seed
    boundary — `RoutingLookup` keeps its `condo_id` argument names
    for clarity inside the product.
    """

    def __init__(self, routing_lookup: RoutingLookup):
        self._routing = routing_lookup

    def travel_minutes(
        self,
        origin_location_id: int | str,
        destination_location_id: int | str,
    ) -> int:
        return self._routing.travel_minutes(
            int(origin_location_id),
            int(destination_location_id),
        )


def make_scheduling_engine(
    rules: SchedulingRules,
    routing_lookup: RoutingLookup,
    conflicts: list[Conflict] | None = None,
    scorer: Scorer | None = None,
) -> SchedulingEngine:
    """Factory — wire the seed engine with our condo-travel adapter.

    `conflicts` / `scorer` default to the seed's `DefaultConflict` /
    `DefaultScorer` (which already encode the source repo's verbatim
    behavior). Pass overrides only if real-estate ever needs them.
    """
    travel_lookup: TravelLookup = CondoTravelLookup(routing_lookup)
    return SchedulingEngine(
        rules=rules,
        travel_lookup=travel_lookup,
        conflicts=conflicts if conflicts is not None else [DefaultConflict()],
        scorer=scorer if scorer is not None else DefaultScorer(),
    )
