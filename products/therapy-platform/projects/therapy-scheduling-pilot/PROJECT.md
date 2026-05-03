# therapy-scheduling-pilot — Project Document

> **This is a living document, not a rigid checklist.**
>
> **Write for a zero-context reader.** §1 inlines the situation; §10 commands are copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** 🅿️ **PARKED** — scaffolded as second-consumer placeholder for `noctusai_lib.domain.scheduling`. Awaits user reactivation when therapy is ready to wire scheduling.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `therapy-scheduling-pilot` — single-product (therapy) scope; lives at `products/therapy-platform/projects/<slug>/`.
- **Related docs:**
  - `KB § PATTERNS/scheduling-seed.md` — the engine + Protocols + wiring recipe.
  - `seed/backend/lib/noctusai_lib/domain/scheduling/engine.py` — the lib.
  - `projects/imobi-scheduling-bot-creation/` — first consumer (real-estate); reference for how to wire.
  - Predecessor: `projects/scheduling-engine-seed/` (closed; lib shipped 2026-05-03).

---

## 1. Context & Purpose

`noctusai_lib.domain.scheduling` shipped 2026-05-03 as the platform's slot-generation engine. Therapy is its second consumer (after `imobi-scheduling-bot-creation`). This project plans the wiring: clinic rooms as locations, professional availability as a custom Conflict, optional cleaning buffer between patients in shared rooms.

Sketch wiring:

```python
from noctusai_lib.domain.scheduling import (
    SchedulingEngine, SchedulingRules, BlockedInterval, ZeroTravelLookup,
)


class ProfessionalAvailabilityConflict:
    """Reject slots when the assigned therapist isn't available."""
    def __init__(self, availability_lookup):
        self._availability = availability_lookup

    def applies(self, slot, context) -> bool:
        return not self._availability.is_available(
            therapist_id=context.target_location_id,  # or via assignee_id seam
            start_at=slot.start_at,
            end_at=slot.end_at,
        )


rules = SchedulingRules(
    timezone=ZoneInfo("America/Sao_Paulo"),
    transition_buffer_minutes=15,  # cleaning between patients
    default_duration_minutes=50,   # therapy session length
    same_location_duration_minutes=50,  # no shortcut for therapy
)

engine = SchedulingEngine(
    rules=rules,
    travel_lookup=ZeroTravelLookup(),  # therapy is single-clinic by default
    conflicts=[DefaultConflict(), ProfessionalAvailabilityConflict(...)],
)
```

---

## 2. Confirmed constraints

(none yet — interrogate user at reactivation)

---

## 3. Design principles

1. **Therapy adopts the seed-lib unmodified.** Differences land as custom `Conflict` / `Scorer` implementations, not seed-lib forks.
2. **Solo-mode therapy is supported.** When a therapist isn't tied to a clinic (solo-practitioner org), treat the therapist's calendar as the location.
3. **No cross-product data sharing.** Therapy queries ONLY its own appointments (per LGPD cross-product block).

---

## 3a. Seed-first analysis

(deferred — the engine is already in seed; this project is consumer wiring inside therapy product scope.)

---

## 6. Implementation phases (sketch — refine at reactivation)

### Phase 0 — Scope confirmation (pending interrogation)
- [ ] Single-clinic vs. multi-clinic at MVP.
- [ ] Cleaning-buffer policy (per-room? global?).
- [ ] Confirm professional availability data source.

### Phase 1 — Custom Conflict + scorer
- [ ] `ProfessionalAvailabilityConflict` per §1 sketch.
- [ ] Optional `RoomCleaningBufferConflict` if per-room buffer differs from global.

### Phase 2 — Service + API
- [ ] `app/services/scheduling.py` glue (DB query → BlockedInterval, engine call).
- [ ] FastAPI route exposing candidate slots.

### Phase 3 — UI integration
- [ ] Frontend consumes slot list + lets patient/therapist confirm.

### Phase 4 — Reschedule path
- [ ] Use `engine.reschedule(original, ...)` for change-appointment flow.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project scaffolded** as Phase 5 sub-task of `projects/scheduling-engine-seed/` close. Status: PARKED, awaits user reactivation when therapy team is ready. Sketch wiring captured in §1. | Claude Opus 4.7 |
