"""Scheduling primitive — slot generation with conflict + scoring.

Lifted from `whatsapp-google-scheduling/app/services/scheduling_service.py`
2026-05-03 via `projects/scheduling-engine-seed/`. Vocabulary generalized
from real-estate (condominium / crew / travel) to platform-neutral
(location / assignee / transition).

Public surface:
- `SchedulingEngine` — main entry point.
- `SchedulingRules` — configuration dataclass.
- `WorkingWindow`, `BlockedInterval`, `Slot`, `SchedulingContext` — value objects.
- `TravelLookup`, `Conflict`, `Scorer` — Protocols for consumer extension.
- `ZeroTravelLookup`, `DefaultConflict`, `DefaultScorer` — sane defaults.

Consumers wire `SchedulingEngine(rules, travel_lookup=...)` with their own
DB-fetched `BlockedInterval` list and call `engine.candidate_slots(...)`.

See `KB § PATTERNS/scheduling-seed.md` for the wiring recipe.
"""

from noctusai_lib.domain.scheduling.engine import (
    BlockedInterval,
    Conflict,
    DefaultConflict,
    DefaultScorer,
    SchedulingContext,
    SchedulingEngine,
    SchedulingRules,
    Scorer,
    Slot,
    TravelLookup,
    WorkingWindow,
    ZeroTravelLookup,
)

__all__ = [
    "BlockedInterval",
    "Conflict",
    "DefaultConflict",
    "DefaultScorer",
    "SchedulingContext",
    "SchedulingEngine",
    "SchedulingRules",
    "Scorer",
    "Slot",
    "TravelLookup",
    "WorkingWindow",
    "ZeroTravelLookup",
]
