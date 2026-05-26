# Scheduling primitive (seed-lib)

> `noctusai_lib.domain.scheduling.SchedulingEngine` — pluggable
> slot-generation engine. Lifted from
> `whatsapp-google-scheduling/app/services/scheduling_service.py` 2026-05-03
> via `projects/scheduling-engine-seed/`. Vocabulary generalized from
> real-estate (condo / crew / travel) to platform-neutral (location /
> assignee / transition).

---

## 1. When to use it

Any product that needs to propose appointment slots subject to:

- Working windows (named time-of-day blocks; lunch is implicit gap between morning/afternoon).
- Conflict rules — overlap with existing intervals + transition buffer when moving between locations.
- Scoring — lower score ranks earlier (default = travel minutes from previous + to next).
- Same-location duration shortcut — back-to-back at same location can use a shorter duration.

Use cases on the platform:

- **Imobi scheduling bot** — first consumer; condo locations + crew assignments + Google-Maps-backed travel adapter.
- **Therapy** — second consumer; clinic rooms as locations + professional availability as a Conflict + cleaning buffer between patients.
- **Daily Life** — future; if scheduling features grow.

Do NOT use it for: cron-style scheduling (one-shot/repeating jobs), full calendar UIs (the engine returns slots, not a calendar), or recurring-appointment generation (out of scope; future work).

---

## 2. Public surface

```python
from noctusai_lib.domain.scheduling import (
    SchedulingEngine,
    SchedulingRules,
    WorkingWindow,
    BlockedInterval,
    Slot,
    SchedulingContext,
    TravelLookup,
    Conflict,
    Scorer,
    ZeroTravelLookup,
    DefaultConflict,
    DefaultScorer,
)
```

| Symbol | Kind | Role |
|---|---|---|
| `SchedulingEngine` | class | Main entry. `candidate_slots(date, target_location_id, existing_intervals, window_name=None, duration_override_minutes=None)` returns sorted `list[Slot]`. |
| `SchedulingRules` | dataclass | Configuration: timezone, transition buffer, default duration, same-location duration, slot grid, working windows. |
| `WorkingWindow` | dataclass | `(name, start, end)`. Names enable per-call filtering. |
| `BlockedInterval` | dataclass | A pre-existing scheduled interval — `(start, end, location_id, assignee_id?)`. |
| `Slot` | dataclass | Engine output — `(start_at, end_at, duration_minutes, score)`. |
| `SchedulingContext` | dataclass | Per-candidate context passed to `Conflict.applies` + `Scorer.score`. |
| `TravelLookup` | Protocol | `travel_minutes(origin, destination) -> int`. Same-id → 0 by convention. |
| `Conflict` | Protocol | `applies(slot, context) -> bool`. Returns `True` to REJECT. |
| `Scorer` | Protocol | `score(slot, context) -> float`. Lower ranks earlier. |
| `ZeroTravelLookup` | class | No-travel default. |
| `DefaultConflict` | class | Mirrors sibling's `_is_valid` (overlap + previous-gap + next-gap). |
| `DefaultScorer` | class | Sums travel from previous-interval and to next-interval. |

---

## 3. Wiring recipe (consumer side)

```python
from datetime import time
from zoneinfo import ZoneInfo
from noctusai_lib.domain.scheduling import (
    SchedulingEngine, SchedulingRules, WorkingWindow, BlockedInterval, TravelLookup,
)


# 1. Define your TravelLookup (or use ZeroTravelLookup if travel is irrelevant)
class GoogleMapsTravelLookup:
    def __init__(self, maps_adapter):
        self._maps = maps_adapter

    def travel_minutes(self, origin_id, destination_id) -> int:
        if origin_id == destination_id:
            return 0
        return self._maps.distance_minutes(origin_id, destination_id)


# 2. Build rules (dataclasses; keep this dataclass instance long-lived per request scope)
rules = SchedulingRules(
    timezone=ZoneInfo("America/Sao_Paulo"),
    transition_buffer_minutes=10,
    default_duration_minutes=90,
    same_location_duration_minutes=60,
    slot_grid_minutes=30,
    working_windows=[
        WorkingWindow(name="morning", start=time(9, 0), end=time(12, 0)),
        WorkingWindow(name="afternoon", start=time(13, 30), end=time(16, 30)),
    ],
)

# 3. Compose the engine
engine = SchedulingEngine(
    rules=rules,
    travel_lookup=GoogleMapsTravelLookup(maps_adapter),
    # conflicts=[DefaultConflict(), MyProfessionalAvailabilityConflict()],
    # scorer=MyPatientPreferenceScorer(),
)

# 4. Fetch existing intervals from your DB into BlockedInterval (consumer concern)
existing = [
    BlockedInterval(
        start=row.start_at,
        end=row.end_at,
        location_id=row.location_id,
        assignee_id=row.assignee_id,
    )
    for row in db.query(...).all()
]

# 5. Ask the engine
slots = engine.candidate_slots(
    requested_date=date.today(),
    target_location_id=property_id,
    existing_intervals=existing,
    window_name="morning",  # optional filter
)
```

---

## 4. Extension points

### Composing multiple Conflict rules

Pass a list. The engine rejects a candidate if **any** rule's `applies` returns `True`.

```python
class ProfessionalAvailabilityConflict:
    def __init__(self, availability_lookup):
        self._availability = availability_lookup

    def applies(self, slot, context) -> bool:
        # context.target_location_id, context.existing_intervals_sorted available.
        # Return True if the assigned professional isn't available at slot.start_at.
        return not self._availability.is_available(slot.start_at)


engine = SchedulingEngine(
    rules=rules,
    travel_lookup=ZeroTravelLookup(),
    conflicts=[DefaultConflict(), ProfessionalAvailabilityConflict(...)],
)
```

### Custom scorer

```python
class PatientPreferenceScorer:
    def __init__(self, preference_lookup):
        self._prefs = preference_lookup

    def score(self, slot, context) -> float:
        # Lower = better. Combine travel (DefaultScorer logic) with preference signal.
        base = DefaultScorer().score(slot, context)
        penalty = self._prefs.dispreference_score(slot.start_at)
        return base + penalty
```

---

## 5. What stays consumer-side

- **DB access.** The engine takes a `list[BlockedInterval]`; the consumer queries its DB and passes them. Sibling shipped a `candidate_slots_for_property()` glue function — that pattern stays consumer-side, e.g., in `app/services/scheduling.py`.
- **Distance / routing adapter.** `TravelLookup` is a Protocol; the consumer wires its own (Google Maps for imobi, no-op for therapy via `ZeroTravelLookup`).
- **Audit logging of slot proposals.** Use `noctusai_lib.domain.ai.tool_audit` if the slot proposal is mediated by an LLM tool call (see `KB § PATTERNS/backend/llm-tool-audit.md`).

---

## 5b. Cancel vs. reschedule

**Cancellation is consumer-side.** The consumer deletes the row from its DB and the next `candidate_slots` call naturally honors the absence — no engine work needed.

**Rescheduling has a dedicated helper.** `engine.reschedule(original, requested_date, target_location_id, all_existing_intervals)` finds replacement slots while excluding `original` from the conflict list. Use when the consumer wants to surface options BEFORE deleting the original (i.e., propose-then-confirm UX).

```python
# Patient asks to move their 10:00-11:30 appointment.
original = BlockedInterval(start=at(10), end=at(11, 30), location_id=room_id)
all_today = [original, ...other_appointments]

candidate_replacements = engine.reschedule(
    original=original,
    requested_date=date.today(),
    target_location_id=room_id,
    all_existing_intervals=all_today,
)
# Show patient the candidate_replacements; on confirm, atomically
# delete original + insert chosen replacement.
```

Reschedule preserves transition buffers + same-location duration shortcut + scoring — the engine's full conflict + scorer pipeline runs on the pruned interval list.

---

## 6. What's NOT in the engine (deferred)

- Holiday calendar / weekend rules (sibling didn't have them; first consumer that needs them files the follow-up).
- Recurring appointments.
- Multi-resource reservation (professional AND room AND equipment) — `BlockedInterval.assignee_id` is a future hook.
- Live-distance scoring via external API — adapter side; lib provides Protocol only.

---

## 7. Tests

`seed/lib/backend/tests/domain/scheduling/test_engine.py` (9 cases):

- 5 ported verbatim from sibling (`test_scheduling_service.py`) with vocabulary translated.
- 4 seed-lib-only tests for the explicit Scorer Protocol surface (zero-neighbors, sum-travel, sort-invariant, ZeroTravelLookup).

Run: `cd seed/lib/backend && pytest tests/domain/scheduling/`.

---

## 8. Related

- `KB § PATTERNS/architect/seed-lib-layout.md` — 6-layer rule (`domain/` is the right placement).
- `KB § 04-SHARED-LIBRARY.md` — catalog entry.
- `projects/scheduling-engine-seed/PROJECT.md` — origin project (deleted at close; see git history).
- First consumer was the `imobi-scheduling` chatbot (wired 2026-05-11), absorbed into `products/social-wiring/app/modules/scheduling/` on 2026-05-16 (`social-wiring-absorption` Wave 4); the scheduling primitive is durable, the consumer moved.
- Future: MCP wrapper as `platform.business.scheduling.suggest_slots` per `mcp-server-fastmcp-switch` Phase 5.
