# scheduling-engine-seed — Project Document

> **This is a living document, not a rigid checklist.**
>
> **Write for a zero-context reader.** Inline context in §1, quote the user in §2, name files with paths in §5, pair every §7 Open Question with an evidence-backed recommendation, make §10 commands copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** Design captured → Phase 0 ready
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `KB § 04-SHARED-LIBRARY.md`, sibling reference at `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/app/services/scheduling_service.py`, `projects/mcp-server-expansion/PROJECT.md` (Phase 5 wraps this lib in `platform.business.scheduling.suggest_slots`).
- **Project slug:** `scheduling-engine-seed` — cross-cutting seed-lib concern. Lives at `projects/<slug>/`.

---

## 1. Context & Purpose

Sibling's `app/services/scheduling_service.py:39-158` is a parametric, fully test-covered appointment-slotting engine: timezone, working windows (morning + afternoon), lunch blocking, same-condominium duration shortcut, travel-buffer enforcement, candidate generation on a 30-minute grid with overlap + buffer validation, scoring by travel distance. The `SchedulingRules` dataclass is the configuration; the engine is data-driven.

Therapy is going to need this — appointment slots for professionals, with cleaning buffers between patients in shared rooms. So is daily-life if it grows scheduling features. Building from scratch means re-deriving the same edge-cases (buffer-includes-the-current-event, lunch-as-implicit-gap, score-by-distance) the sibling already validated empirically.

This project lifts the engine to `noctusai_lib.domain.scheduling`, generalizes the domain vocabulary (rooms / professionals instead of condos / crew, cleaning-or-prep buffer instead of travel buffer), and ships the sibling's test suite as the validation evidence carried forward.

---

## 2. Confirmed constraints

- **Priority #3 in the absorption batch** — user confirmed in 2026-05-03 session. Lands after WhatsApp absorption + LLM tool audit foundations are in motion.
- **Lift to seed, therapy is first consumer** — analyst's framing accepted. Per CLAUDE.md seed-first principle, the engine is universal; the consumer-specific data wiring stays product-side.
- **Preserve parametric shape** — sibling's `SchedulingRules` dataclass is the design surface. Don't bake real-estate vocabulary into the lib; rename to generic terms (working windows, conflict buffer, slot duration variants).

---

## 3. Design principles

1. **Vocabulary translation, not redesign.** Rename: `condominium` → `location`, `crew` → `assignee`, `travel_buffer_minutes` → `transition_buffer_minutes`, `same_condominium_duration` → `same_location_duration`. The math is unchanged.
2. **Conflict checks are pluggable.** Sibling has overlap + travel-buffer. Therapy adds professional-availability + room-availability. Provide a `Conflict` protocol; consumers compose conflict rules.
3. **Time grid is configurable.** Sibling hardcodes 30-min spacing. Lift as `slot_grid_minutes` parameter (default 30).
4. **Candidate scoring is a strategy.** Sibling scores by travel distance. Therapy may score by stylist preference / patient affinity. Strategy injection at construction.
5. **No DB coupling in the lib.** Sibling reads existing appointments via repository inside the service; lift the service to take a list of `BlockedInterval` objects. Consumer queries the DB and passes the list.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

1. **Is the contract identical for every product?** YES — slot-generation contract is universal once vocabulary generalizes.
2. **Is the data source product-specific?** YES — each consumer queries its own appointments / professional availability / room calendar; container is seedable, data is product-injected.
3. **Is the placement product-specific?** NO — `noctusai_lib/domain/scheduling/`.
4. **Is the visibility / permission rule the same?** YES — engine is pure; visibility lives in the consumer's data query.
5. **Does the seam already exist in seed?** NO — `noctusai_lib/domain/scheduling/` is new.
6. **Default-on or opt-in?** OPT-IN — only products with scheduling features wire it.

**Litmus — per-product code count this design requires:** [x] **A small section** — consumer supplies rules instance + appointment-query function + (optional) custom Conflict + (optional) custom scorer. Acceptable for product-specific data sources.

**Phase plan implications:** §6 phases work in `noctusai_lib/domain/scheduling/` and `KB`. **No phase walks through products.**

---

## 4. Scope

**In scope:**

- `noctusai_lib/domain/scheduling/engine.py` — `SchedulingEngine`, `SchedulingRules`, `BlockedInterval`, `Conflict` protocol, default conflict rules (overlap + transition buffer).
- `noctusai_lib/domain/scheduling/scoring.py` — default `Scorer` protocol + simple time-distance scorer.
- Sibling's test suite ported as the validation evidence: `tests/test_scheduling_service.py` → `seed/backend/lib/tests/domain/scheduling/test_engine.py` (vocabulary translated; assertions preserved).
- `KB § PATTERNS/scheduling-seed.md` — wiring recipe + when to use + extension points.
- MCP wrapper coordination: `projects/mcp-server-expansion/` Phase 5 wraps this lib as `platform.business.scheduling.suggest_slots`.

**Out of scope (for now — with reason):**

- Therapy first-consumer wiring — its own follow-up project (`products/therapy-platform/projects/therapy-scheduling-pilot/`).
- Holiday calendar / weekend rules — sibling doesn't have them; add when first consumer needs them.
- Recurring appointments — outside sibling's scope.
- Multi-resource slot reservation (e.g., "professional AND room AND equipment") — extension point left for future.
- Routing distance score by external API — sibling has it via Google Maps; lib provides protocol but ships only static-distance default scorer. Live-distance scoring stays in adapter at consumer side.

---

## 5. Architecture / Data Model

### 5.1 The there → here map

| There (`whatsapp-google-scheduling/`) | Here (`noctusai/seed/backend/lib/noctusai_lib/`) | Notes |
|---|---|---|
| `app/services/scheduling_service.py:SchedulingService` (lines 39-158) | `domain/scheduling/engine.py::SchedulingEngine` | Vocabulary generalized per §3 principle 1. |
| `app/services/scheduling_service.py:SchedulingRules` (lines 19-28) | `domain/scheduling/engine.py::SchedulingRules` | Field renames; semantics preserved. |
| `app/services/scheduling_service.py:candidate_slots_for_property()` (lines 160-197) | (DROP — DB coupling lives in consumer; lib's `SchedulingEngine.candidate_slots(rules, blocked, ...)` takes pre-fetched data) | |
| `tests/test_scheduling_service.py` (lines 34-100) | `seed/backend/lib/tests/domain/scheduling/test_engine.py` | Vocabulary translated; cases preserved verbatim. |
| `mcp_server/tools/noctus/scheduling/suggest_slots.py` | (DEFER — `projects/mcp-server-expansion/` Phase 5 wraps it as `platform.business.scheduling.suggest_slots`) | |

### 5.2 Vocabulary mapping

| Sibling | Seed lib |
|---|---|
| `condominium_id` | `location_id` |
| `crew` / `crew_id` | `assignee` / `assignee_id` |
| `travel_buffer_minutes` | `transition_buffer_minutes` |
| `same_condominium_duration` | `same_location_duration` |
| `standard_duration` | `default_duration` |
| `morning_start / morning_end / afternoon_start / afternoon_end` | preserved verbatim (working windows are universal) |

### 5.3 Engine contract (sketch)

```python
@dataclass
class SchedulingRules:
    timezone: str
    working_windows: list[tuple[time, time]]  # generalized (sibling had morning + afternoon)
    default_duration_minutes: int = 90
    same_location_duration_minutes: int = 60
    transition_buffer_minutes: int = 10
    slot_grid_minutes: int = 30  # NEW config; sibling hardcoded 30

@dataclass
class BlockedInterval:
    start: datetime
    end: datetime
    location_id: str | None = None
    assignee_id: str | None = None

class Conflict(Protocol):
    def applies(self, slot: Slot, blocked: BlockedInterval) -> bool: ...

class Scorer(Protocol):
    def score(self, slot: Slot, context: dict) -> float: ...

class SchedulingEngine:
    def __init__(self, rules: SchedulingRules, conflicts: list[Conflict] | None = None, scorer: Scorer | None = None): ...
    def candidate_slots(self, date: date, blocked: list[BlockedInterval], duration: int | None = None) -> list[Slot]: ...
```

---

## 6. Implementation phases

### Phase 0 — Audit before any code lands

- [ ] Read sibling's `scheduling_service.py` + `tests/test_scheduling_service.py` end-to-end.
- [ ] Identify any test fixture / helper coupled to real-estate vocabulary that needs translation.
- [ ] Verify `noctusai_lib/domain/scheduling/` does not exist (or document existing partial seam).

### Phase 1 — Engine + rules + conflicts

- [ ] Create `seed/backend/lib/noctusai_lib/domain/scheduling/engine.py`.
- [ ] Implement `SchedulingRules`, `BlockedInterval`, default conflict (overlap + transition buffer).
- [ ] Implement `SchedulingEngine.candidate_slots(...)` with grid generation + conflict filtering.

### Phase 2 — Scoring strategy

- [ ] Implement `Scorer` protocol + default time-distance scorer.
- [ ] Wire `SchedulingEngine` to use injected scorer (default supplied if `None`).

### Phase 3 — Tests ported from sibling

- [ ] Port every case in sibling's `test_scheduling_service.py` to `seed/backend/lib/tests/domain/scheduling/test_engine.py`.
- [ ] Translate vocabulary in test data (condo IDs → location IDs).
- [ ] Tests must pass.

### Phase 4 — KB pattern doc

- [ ] Write `KB § PATTERNS/scheduling-seed.md` covering: rules definition, conflict composition, scoring strategy, consumer wiring recipe, examples.
- [ ] Update `KB § INDEX.md`.
- [ ] Update `CLAUDE.md §3 Map`.
- [ ] Three-way sync.

### Phase 5 — Final verification + handoff

- [ ] `pytest seed/backend/lib/tests/domain/scheduling/` — green.
- [ ] `bash scripts/verify-kb-sync.sh` — green.
- [ ] Coordinate with `projects/mcp-server-expansion/` Phase 5 for the MCP wrapper.
- [ ] Coordinate with `projects/imobi-scheduling-bot-creation/` Phase 6 (first product consumer of this engine).
- [ ] Scaffold therapy second-consumer follow-up project at `products/therapy-platform/projects/therapy-scheduling-pilot/` (therapy is the second consumer; imobi-scheduling is the first).

### Phase 6 — Cancellation + reschedule support (folded from sibling `cancellation-rescheduling` PROJECT)

- [ ] Engine API supports **rescheduling** as a first-class operation: `SchedulingEngine.reschedule(existing_slot, blocked_intervals)` returns candidate replacement slots subject to the same conflict + scoring rules.
- [ ] Cancellation is consumer-side concern (no engine work needed beyond ensuring removed appointments are honored in the next `blocked` query).
- [ ] Document the cancel-vs-reschedule distinction in `KB § PATTERNS/scheduling-seed.md`.
- [ ] Tests: reschedule preserves transition buffers + same-location duration shortcut + scoring.

---

## 7. Open questions

1. **Working windows: list of (start, end) pairs vs. start/end/lunch decomposition?** Recommendation: list of pairs (more general — therapy may want 8:00-11:30 / 12:30-17:00 / 18:00-20:00 evening window). Decided in Phase 1.
2. **Slot grid: per-rules or per-call?** Recommendation: per-rules default with per-call override. Decided in Phase 1.
3. **Therapy's "professional availability" — is it a Conflict or a separate feature?** Recommendation: Conflict — the engine treats every blocking constraint uniformly. Decided when therapy wires in follow-up project.
4. **State machine for appointment requests (folded sibling idea `state-machine-for-requests`).** Recommendation: **out of scope here** — the engine is stateless; state machines belong in the consumer product (`projects/imobi-scheduling-bot-creation/` §7 Q6). Decided per consumer.

---

## 8. Dependencies & blockers

- **`projects/mcp-server-expansion/` Phase 5** — depends on this project's lib being importable (NOT blocking; can be parallel).
- **No DB / infrastructure dependency.**

---

## 9. Success criteria

- [ ] `noctusai_lib/domain/scheduling/` exists with engine + rules + scorer.
- [ ] All sibling test cases pass against the new lib (vocabulary translated).
- [ ] `KB § PATTERNS/scheduling-seed.md` exists and is indexed / pointed-to.
- [ ] First consumer wired (`projects/imobi-scheduling-bot-creation/` Phase 7 imports + configures `SchedulingEngine`).

---

## 10. How to use this plan

```bash
# Sibling reference
cat ~/Documents/repository/NoctusAI/whatsapp-google-scheduling/app/services/scheduling_service.py
cat ~/Documents/repository/NoctusAI/whatsapp-google-scheduling/tests/test_scheduling_service.py

# Lib + tests
pytest seed/backend/lib/tests/domain/scheduling/

# KB sync
bash scripts/verify-kb-sync.sh
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial project drafted; user confirmed priority #3 (lift sibling scheduler to seed). First consumer revised: `projects/imobi-scheduling-bot-creation/` (the new noc product reimplementing the bot on our patterns) is the named first consumer; therapy is future. | claude-opus-4-7 |
| 2026-05-03 | Folded sibling's `cancellation-rescheduling` planning into Phase 5 (engine support for reschedule scenarios). Added §7 hooks for sibling's `state-machine-for-requests` idea. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

The sibling repo (`~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`) WILL BE DELETED by the user once the absorption batch completes:

- **All sibling-path references in this PROJECT.md are execution-scoped** — vanish when this project closes.
- **`KB § PATTERNS/scheduling-seed.md` references our lib only.**
- **`noctusai_lib/domain/scheduling/engine.py` is freshly authored** on the generalized vocabulary (location/assignee/transition_buffer); sibling is design-reference for behavior parity, not a runtime dep.
- **Tests stand alone** under `seed/backend/lib/tests/domain/scheduling/`. Test cases are inspired by sibling's `tests/test_scheduling_service.py` but written against our types.

### Future-work hook captured from sibling

- **`state-machine-for-requests`** — typed state machine for `appointment_request` transitions (collecting → awaiting_confirmation → scheduled). NOT in this project; lives in the consuming product's domain (`projects/imobi-scheduling-bot-creation/` could add it as a refinement, or it becomes its own follow-up if multiple consumers want it).
| 2026-05-03 | Folded sibling `cancellation-rescheduling` PROJECT into §6 Phase 6 (intent variants + reschedule routes through same slot-suggester). Added §12 No-leftovers constraint. Cross-referenced `imobi-scheduling-bot-creation` as the natural first consumer alongside therapy. | claude-opus-4-7 |
