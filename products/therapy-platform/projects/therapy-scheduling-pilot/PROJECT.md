# therapy-scheduling-pilot — Project Document

> **This is a living document, not a rigid checklist.**
>
> **Write for a zero-context reader.** §1 inlines the situation; §10 commands are copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03 (Phase 0 interrogation complete)
- **Status:** ✅ **COMPLETE — all 5 phases shipped 2026-05-03.** Backend pytest **1176 passed** (+25 pilot tests over baseline 1151). Frontend Vitest **4/4 passed**. Vite build clean (4.40s). Keeper review **0 issues**. Manual GCal-OAuth QA deferred to user (requires Google Cloud Console client setup). Ready for project close (final commit + folder delete).
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `therapy-scheduling-pilot` — single-product (therapy) scope; lives at `products/therapy-platform/projects/<slug>/`.
- **Related docs:**
  - `KB § PATTERNS/scheduling-seed.md` — the engine + Protocols + wiring recipe.
  - `seed/lib/backend/noctusai_lib/domain/scheduling/engine.py` — the lib.
  - `seed/lib/backend/noctusai_lib/integrations/google_calendar/__init__.py` — adapter Protocol + Fake (real adapter deferred — see §8).
  - `projects/imobi-scheduling-bot-creation/` — first consumer (real-estate); reference for how to wire.
  - `products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md` — parallel agent project; pilot avoids file collisions per §8.
  - Predecessor: `projects/scheduling-engine-seed/` (closed; lib shipped 2026-05-03).
  - Follow-up to file at Phase 0 close: `projects/google-calendar-real-adapters/` (DRY recurrence — N=2 consumers needing OAuth adapter).

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

Decisions captured during the 2026-05-03 Phase 0 interrogation. **Future agents inherit the reasoning, not just the outcome.**

- **Clinic scope at MVP — multi-clinic + solo, day one.** User selected the recommended option. *Reasoning:* the schema already supports both — `therapy.availability_slots.clinic_id` is nullable, `therapy.appointments.clinic_id` is nullable, `therapy.rooms.clinic_id` is FK to `therapy.clinics`. The engine takes the same `BlockedInterval` list either way; only difference is whether `room_bookings` is filtered by clinic. Cost of supporting both ≈ cost of supporting one. Rules out scope-narrowing temptation in Phase 2.
- **Cleaning / transition buffer — global per-clinic, default 15 min.** User selected the recommended option. *Reasoning:* `therapy.rooms.capacidade DEFAULT 1` shows 1-patient rooms are the norm; per-room buffer differences are N=1 today. Lands as `therapy.clinic_settings.transition_buffer_minutes INT DEFAULT 15` (existing table at migration 001 line 105 — additive column). Engine builds with `SchedulingRules(transition_buffer_minutes=<from clinic_settings>)`. Per-room override deferred as `accept-with-rationale` until a clinic with mixed room types appears, at which point a `RoomCleaningBufferConflict` wraps the global default.
- **Professional-availability data source — Internal + Google Calendar two-way.** User selected option 2 over the recommended internal-only. *Reasoning given by user choice:* catches off-platform bookings the therapist sees on their phone calendar; the `appointments.google_event_id` column (migration 001 line 233) shows the integration was always intended. Two-way means: (a) READ GCal events as additional `BlockedInterval`s during slot generation, (b) WRITE confirmed appointments to GCal as events.
- **Google Calendar adapter strategy — file the seed real-adapter project NOW; pilot uses Fake until it lands.** User selected the recommended option. *Reasoning:* seed shipped only `FakeCalendarAdapter` at Phase 0 time, with the real OAuth/service-account adapter explicitly deferred. Therapy + imobi-scheduling-bot-creation both need it = **N=2 → DRY recurrence triage point → formalize**. **UPDATE 2026-05-03:** the seed project (`projects/google-calendar-real-adapters/`) was scaffolded AND shipped Phases 1-3 same day by a parallel agent — `GoogleCalendarOAuthAdapter` + `GoogleCalendarServiceAccountAdapter` + `CalendarCredentialResolver` Protocol now live in `noctusai_lib.integrations.google_calendar`. **Pilot can wire the real adapter from Phase 2 onwards — no Fake-then-swap detour.** Tests still use Fake (resolver returns None → falls back to Fake automatically).
- **OAuth refresh-token storage — pgcrypto + Supabase Vault key + 7-day re-auth requirement.** User answered §7 Q1 directly: *"pgcrypto + supabase vault key + 7 day-refresh timer, making the user have to reauth every 7 days, as a safety feature"*. *Reasoning:* OAuth refresh tokens are credentials-grade secrets per LGPD Art. 46. Defense-in-depth: (a) column-level encryption with Vault-rotatable key (DB row leak ≠ token leak), (b) 7-day re-auth window enforced by `therapy.gcal_authorization_is_fresh()` helper (compromise window bounded), (c) existing therapy.therapist_profiles RLS (only the owning therapist + platform_admin can read). Three independent factors required for compromise. Migration 011 ships the Vault secret bootstrap + helper functions.

---

## 3. Design principles

1. **Therapy adopts the seed-lib unmodified.** Differences land as custom `Conflict` / `Scorer` implementations, not seed-lib forks.
2. **Solo-mode therapy is supported.** When a therapist isn't tied to a clinic (solo-practitioner org), treat the therapist's calendar as the location.
3. **No cross-product data sharing.** Therapy queries ONLY its own appointments (per LGPD cross-product block).

---

## 3a. Seed-first analysis

Required by `feedback_seed_first_at_authoring_time` even for single-product scope.

1. **Is the contract identical for every product?** Partially — the engine + Protocols ARE identical (in `noctusai_lib.domain.scheduling`). The product-specific pieces (`ProfessionalAvailabilityConflict`, the data-source adapters that read therapy tables, the API DTO) live in this product. Other products that adopt scheduling will write their own Conflict/data-source pair against the same Protocol surface. **Per-product code count for the engine: 0** (consumed unmodified). Per-product wiring count: 1 service file.
2. **Is the data source product-specific?** YES — `therapy.availability_slots`, `therapy.appointments`, `therapy.room_bookings`, `therapy.clinic_settings` are therapy-only tables.
3. **Is the placement product-specific?** YES — pilot wiring lives under `products/therapy-platform/backend/app/`.
4. **Visibility / permission rule?** Per-product RLS (existing therapy policies cover the read paths). Slot-generation is read-only against existing rows; no new RLS needed for Phase 1-2.
5. **Does the seam already exist in seed?** YES for the engine (`SchedulingEngine`, `Conflict` Protocol, `BlockedInterval`, etc.) and the Calendar adapter Protocol. NO real Google Calendar adapter — see §8.
6. **Default-on or opt-in?** N/A — products opt into the engine via consuming the lib; nothing auto-mounts.

**Litmus — per-product code count this design requires:** [x] **A small section** — one service file (`app/services/scheduling.py`), one router (`app/routers/scheduling.py`), one migration (additive column on existing `clinic_settings` + GCal token storage), one custom `ProfessionalAvailabilityConflict` class. The engine + Calendar adapter are zero-modification consumed.

**Phase plan implications:** §6 phases work entirely in `products/therapy-platform/`. **No phase walks through other products.** The only seed touch is the new `google-calendar-real-adapters` project (filed at Phase 0 close as an independent seed project, not folded into pilot scope).

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as work progresses.

**Phase status-icon convention:** _(none)_ pending, ⏳ in progress, ✅ complete, ❌ blocked.

**Improvement capture happens during steps. Proposal authoring happens at end of phase.** One bundled proposal per phase, applied-inline-then-deleted by default; formal proposal only for scheduled / human-approval items.

---

### Phase 0 — Scope confirmation ✅

- [x] Q1 single vs. multi-clinic — **multi-clinic + solo, day one**.
- [x] Q2 cleaning-buffer policy — **global per-clinic, default 15 min** (`clinic_settings.transition_buffer_minutes`).
- [x] Q3 professional-availability data source — **internal `availability_slots` + `appointments` PLUS Google Calendar two-way**.
- [x] Q4 (surfaced during Q3) GCal adapter strategy — **file `projects/google-calendar-real-adapters/` separately; pilot uses Fake until it lands**.
- [x] File `projects/google-calendar-real-adapters/PROJECT.md` — scaffolded as PARKED, full §1-§11 with sketch phases, awaits reactivation by either consumer.
- [x] Capture Phase 0 **Improvements** — see end-of-section block below.

**Improvements captured during Phase 0:**
- Pausing on Q3's "yes-to-recommendation" path to verify the seed adapter actually existed turned a silent scope expansion (we'd have shipped a pilot that couldn't run in production) into an explicit DRY-formalize decision (the new GCal real-adapter project). Confirms the `feedback_no_silent_errors` shape: ambiguity surfaced as a 4th question rather than ignored. Worth applying as a standing pattern to any "let's just consume the seed" decision: BEFORE locking, verify the seed concretely ships what the consumer needs, not just the Protocol.
- The pilot's Phase 0 produced **two artifacts** (this PROJECT.md update + the new `google-calendar-real-adapters/PROJECT.md`) without writing any product code — exactly what Phase 0 is for. Cadence respected.

---

### Phase 1 — Migration + custom Conflict ✅

**Files (all net-new — no collision with parallel `therapy-platform-wiring` agent):**
- `products/therapy-platform/backend/migrations/011_scheduling_pilot.sql` *(011 confirmed at execution time — wiring agent reserved 010 for `rejection_audit`)*.
- `products/therapy-platform/backend/app/services/scheduling/__init__.py`
- `products/therapy-platform/backend/app/services/scheduling/conflicts.py`
- `products/therapy-platform/backend/tests/services/test_scheduling_conflicts.py`
- *Engine + Calendar adapter coverage already lives in `seed/lib/backend/tests/`; pilot adds product-side coverage only.*

**Sub-tasks:**
- [x] Write migration `011_scheduling_pilot.sql`. Adds: (1) `clinic_settings.transition_buffer_minutes INT NOT NULL DEFAULT 15` (Q2), (2) `therapist_profiles.gcal_refresh_token_encrypted BYTEA` + `gcal_calendar_id TEXT` + `gcal_authorized_at TIMESTAMPTZ` (Q3 + §2 encryption decision), (3) Vault secret bootstrap (`gcal_token_key`, idempotent), (4) `therapy.encrypt_gcal_token(text)` / `therapy.decrypt_gcal_token(bytea)` helpers (SECURITY DEFINER, search_path locked, `extensions.pgp_sym_*`), (5) `therapy.gcal_authorization_is_fresh(timestamptz)` 7-day re-auth check.
- [x] Apply migration via `mcp__claude_ai_Supabase__apply_migration`. Smoke test verified: vault secret created, 3 gcal columns added, freshness check correct on past/recent/NULL inputs, encrypt→decrypt round-trip returned `test_refresh_token_xyz`.
- [x] Implement `ProfessionalAvailabilityConflict(Conflict)` in `app/services/scheduling/conflicts.py`. Closes over a `Callable[[date], list[AvailabilityWindow]]` supplied by the service layer (date arithmetic / DB query / day-of-week conversion live there, not in the conflict). Engine note honored: therapist_id captured by the lookup closure, not pulled from `context.target_location_id` (which is the location). `AvailabilityWindow` dataclass added (frozen, half-open intervals, `is_blocked` flag for one-off overrides).
- [x] Unit tests in `tests/services/test_scheduling_conflicts.py` — 8 cases: inside window (False), no window (True), block overlapping (True), specific-date block overrides recurring (True), half-open boundary at end (False), partial overlap past end (True), lookup-receives-date contract, empty list (True). All passing in 0.09s.
- [x] Full backend pytest: **1151 passed, 1 warning, 9.86s** — no regressions.
- [x] `cli.py --review --product therapy-platform`: **0 issues found**, no proposals to author.

**Improvements captured during Phase 1:**
- The standing check fired in real time during this phase: when the migration's first draft used `public.pgp_sym_encrypt`, the `list_extensions` MCP call surfaced that pgcrypto lives in the `extensions` schema on Supabase — schema-qualified to `extensions.pgp_sym_*` before applying. Verifying the seed/runtime *concretely* ships at the path you assume = `feedback_verify_seed_ships_it` extended to environments, not just seed modules.
- `SecurityDefiner` + `SET search_path = ''` is a small recurring pattern across migrations that touch Vault-backed secrets (will appear in any other product that adopts pgcrypto+Vault). Worth absorbing as a seed migration helper if a third consumer shows up; for now, **N=1 in repo** so no action yet — flagging here as a future N=2 trigger.
- Conflict shape (lookup-Callable vs. inline DB query) was a small judgment call. Closure-injection won because it keeps the conflict pure-functional and trivially unit-testable (no DB mock, no row fixtures). Same shape recommended for any future product-side `Conflict` implementations.
- The N=2 DRY-recurrence call to file `google-calendar-real-adapters` — and the parallel agent's same-day delivery — validated the standing check end-to-end. Pilot Phase 3 collapsed from "wait + swap" to "wire real adapter from Phase 2" before Phase 1 even closed.

---

### Phase 2 — Service + API endpoint ⏳

**Files (all net-new — no collision):**
- `products/therapy-platform/backend/app/services/scheduling/service.py` — DB → `BlockedInterval[]` mapper + engine call + DTO mapper.
- `products/therapy-platform/backend/app/services/scheduling/calendar_sync.py` — Fake-adapter-backed read/write to GCal; injectable so Phase 1-2 tests run against `FakeCalendarAdapter`.
- `products/therapy-platform/backend/app/routers/scheduling.py` — new router; mounted via the seed `standard_routers=[..., "scheduling"]` seam (or `extra_routers=[scheduling.router]` if the slug isn't in the seed allow-list — confirm at execution time).
- `products/therapy-platform/backend/tests/services/test_scheduling_service.py`
- `products/therapy-platform/backend/tests/routers/test_scheduling_router.py`

**Sub-tasks:**
- [ ] Implement `list_blocked_intervals(therapist_id, clinic_id, window_start, window_end, db)` — reads `therapy.appointments` (status NOT IN cancelled/late_cancelled/no_show) → `BlockedInterval(reason="appointment", ...)`; reads `therapy.availability_slots WHERE is_blocked=true AND specific_date BETWEEN ...` → `BlockedInterval(reason="manual_block", ...)`; reads GCal events via the Calendar adapter → `BlockedInterval(reason="gcal_event", ...)`.
- [ ] Implement `generate_candidate_slots(therapist_id, clinic_id, window_start, window_end, duration_minutes=50, db, calendar_adapter)` — builds `SchedulingRules` from the clinic's `transition_buffer_minutes`, instantiates `SchedulingEngine(rules, ZeroTravelLookup(), [DefaultConflict(), ProfessionalAvailabilityConflict(...)])`, returns ranked slots.
- [ ] Implement `book_appointment(slot, patient_id, therapist_id, clinic_id, db, calendar_adapter)` — inserts into `therapy.appointments` AND writes a GCal event, captures `google_event_id` on the appointment row. Idempotent via `EventInput.request_id`.
- [ ] FastAPI router with two endpoints (NEW URL prefix `/api/scheduling` to avoid the wiring agent's `/api/availability` and `/api/appointments` surfaces):
    - `GET /api/scheduling/candidates?therapist_id=...&clinic_id=...&window_start=...&window_end=...&duration_minutes=50` → `[Slot]`
    - `POST /api/scheduling/appointments` body `{slot, patient_id, therapist_id, clinic_id?}` → created appointment.
- [ ] Service unit tests (mock DB + `FakeCalendarAdapter`) — slot generation respects buffer, conflicts reject correctly, GCal events become `BlockedInterval`s, booking writes appointment + GCal event.
- [ ] Router tests — auth boundary (therapist can request own slots; admin can request anyone's; patient cannot), happy path, empty-window edge.
- [ ] `noctus.dev.lgpd_flag(...)` call: appointment data crossing into Google Calendar is a personal-data export → flag for LGPD review (per `feedback_lgpd_first`).
- [ ] Run `python mcp/noctusai/cli.py --review products/therapy-platform`.
- [ ] Capture **Improvements**; flip to ✅.

---

### Phase 3 — UI integration + real-adapter manual QA ⏳ (manual QA deferred — see notes)

**Prerequisite update 2026-05-03:** `projects/google-calendar-real-adapters/` Phases 1-3 shipped same day (status ✅ DELIVERED) — `GoogleCalendarOAuthAdapter` lives in seed. The "real-adapter swap" sub-task collapses; Phase 2 wires the real adapter directly via the `TherapyGcalCredentialResolver`, Phase 3 just exercises it end-to-end through the UI.

**Sub-tasks:**
- [ ] Frontend page: path TBD by cross-referencing `therapy-platform-wiring` Phase 0 gap-table — open files NOT on their touch list. Calls `/api/scheduling/candidates`, renders slot list, `POST /api/scheduling/appointments` on confirm.
- [ ] OAuth-redirect frontend flow — when `gcal_authorization_is_fresh()` returns false, redirect therapist to Google OAuth UI; on callback, write `gcal_refresh_token_encrypted` (via `therapy.encrypt_gcal_token` RPC) + `gcal_authorized_at = now()`.
- [ ] Component test (Vitest) for the slot picker.
- [ ] Manual QA — connect a real Google Calendar (run the OAuth flow), book a real session, verify event appears in the connected calendar, manually add an event in GCal, verify slot generator excludes that window. Verify the 7-day re-auth: artificially set `gcal_authorized_at` to 8 days ago, confirm the flow forces re-OAuth.
- [ ] `cd products/therapy-platform/frontend && npx vite build` — clean.
- [ ] Capture **Improvements**; flip to ✅.

---

### Phase 4 — Reschedule path ⏳ (collapsed into Phase 2 router — single PATCH endpoint)

- [ ] Service: `reschedule_appointment(appointment_id, new_slot, db, calendar_adapter)` — uses `engine.reschedule(original, new_window)` (per the engine API) + `calendar_adapter.update_event(...)`.
- [ ] Router endpoint: `PATCH /api/scheduling/appointments/{id}` body `{slot}`.
- [ ] Tests (service + router).
- [ ] Manual QA — reschedule, verify GCal event updates in place (no duplicate).
- [ ] `cd products/therapy-platform/backend && pytest tests/` — full suite green.
- [ ] Capture **Improvements**; flip to ✅. **Project close** — final commit + push per `feedback_no_auto_commit` carve-out.

---

## 7. Open questions

1. ~~**Per-therapist GCal OAuth credential storage** — Phase 1 migration encryption strategy?~~ — **DECIDED 2026-05-03 (during Phase 1 execution):** pgcrypto-encrypted BYTEA column, key in Supabase Vault, **plus** 7-day re-auth requirement (token expires from app's POV after 7 days; therapist must re-consent). User quote: *"pgcrypto + supabase vault key + 7 day-refresh timer, making the user have to reauth every 7 days, as a safety feature"*. Migration 011 ships the Vault bootstrap + helpers. Defense-in-depth: encryption + re-auth window + RLS = 3 independent factors.
2. **Patient self-booking vs. therapist-initiated only at MVP** — `POST /api/scheduling/appointments` could be open to patients (matching → propose → confirm) or therapist-only (admin-style booking). The therapy-platform has both flows scaffolded. *(Phase 2.)* Recommendation: **therapist-initiated only at MVP** — fewer auth-boundary edge cases; patient self-booking gets its own follow-up project once the matching flow is wired by `therapy-platform-wiring`. Decided by: Claude during Phase 2, user can override.
3. **Frontend page placement** — depends on what `therapy-platform-wiring` Phase 0 gap-table puts on the therapist-portal touch list. *(Phase 3.)* Decided by: cross-reference with wiring agent's Phase 0 output before opening frontend files.

---

## 8. Dependencies & blockers

- **~~`google-calendar-real-adapters` follow-up project~~** — **NO LONGER A BLOCKER.** Project shipped Phases 1-3 same day (status ✅ DELIVERED). `GoogleCalendarOAuthAdapter` + `GoogleCalendarServiceAccountAdapter` + `CalendarCredentialResolver` Protocol live in `noctusai_lib.integrations.google_calendar`. Pilot wires the real adapter from Phase 2; tests still use Fake (resolver returns None → factory falls back automatically).
- **Parallel agent: `products/therapy-platform/projects/therapy-platform-wiring/`** — pilot AVOIDS the wiring agent's targets:
  - DO NOT touch: `app/routers/availability.py`, `app/routers/appointments.py`, `app/routers/rooms.py`, `app/services/availability_service.py`, `app/services/appointment_service.py`, `app/services/room_service.py`.
  - DO NOT take migration number `010` (reserved by wiring agent for `010_rejection_audit.sql`); pilot uses next free at execution time.
  - DO NOT touch the shared identity resolver in `noctusai_lib/integrations/supabase_identity.py` (wiring agent Phase 1).
  - Pilot files only NEW files: `app/services/scheduling/*`, `app/routers/scheduling.py`, new migration, new tests.
  - Frontend: defer Phase 3 page placement until wiring agent's Phase 0 gap-table is published, then open files NOT on their touch list.
  - Per `feedback_parallel_agent_collision_protocol`: if a non-trivial revert happens, STOP, do NOT file a collision-report project, catalog the deferred work in `KB § PATTERNS/accept-with-rationale.md`, wait for the parallel project to close.
- **Supabase MCP access** — already granted via blanket approval; used for migration application in Phase 1.
- **`clinic_settings` table exists** — confirmed at migration `001_therapy_platform.sql:105`. Pilot adds one column additively.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project scaffolded** as Phase 5 sub-task of `projects/scheduling-engine-seed/` close. Status: PARKED, awaits user reactivation when therapy team is ready. Sketch wiring captured in §1. | Claude Opus 4.7 |
| 2026-05-03 | **Phases 2-4 shipped same session.** *(User instruction: "ram through it all".)* **Phase 2 (Service + API):** new `app/services/scheduling/{credentials,calendar_sync,service}.py` modules + `app/routers/scheduling.py` mounted via `routers=[..., scheduling.router]` in main.py. Service tests + router tests covering auth boundary, GCal-write resilience (appointment persists when GCal write fails), Fake-fallback resolver, clinic-buffer reads. **Phase 3 (UI + OAuth shape):** `frontend/src/pages/therapist/Scheduling.tsx` + `frontend/src/hooks/useScheduling.ts` + Vitest hook tests. Backend OAuth endpoints (`/api/scheduling/gcal/{authorize,callback}`) using httpx for Google token exchange; tests mock at the httpx boundary per `feedback_no_monkeypatching_in_tests`. **Phase 4 (Reschedule):** PATCH endpoint `cancel + book` composition (no `update_event` on the seed CalendarAdapter Protocol — flagged as future N=2 trigger). Total **34 pilot-specific tests** added; full backend pytest **1176 passed** (no regressions). Frontend vite build clean. Manual GCal QA deferred (needs Google Cloud Console OAuth client setup). | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1 in progress — two same-day expansions absorbed.** (a) §7 Q1 closed: user picked **pgcrypto + Vault key + 7-day re-auth** for OAuth refresh-token storage. Migration 011 rewritten to ship encryption helpers (`therapy.encrypt_gcal_token`, `decrypt_gcal_token`, `gcal_authorization_is_fresh`) + Vault secret bootstrap, not just plain TEXT columns. (b) `projects/google-calendar-real-adapters/` shipped Phases 1-3 same-day by parallel agent — pilot's "Fake-then-swap-to-real" two-step collapses to "wire real adapter from Phase 2". §6 Phase 1 sub-tasks updated; Phase 3 sub-tasks updated; §8 GCal blocker struck through; §7 Q1 marked DECIDED. **Standing-check rule formally adopted via three-way sync** — KB § 03-SEED-ARCHITECTURE.md § Verify-the-seed-ships-it test added; CLAUDE.md universal-rule pointer added; memory `feedback_verify_seed_ships_it.md` + index line. The same-day adapter delivery validates the rule's other path: when N=2+ consumers need a gap, the right move is to file the seed project — and sometimes it ships fast enough to retire the workaround in the same session. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 0 interrogation complete.** Status: PARKED → 🚧 Phase 0 in progress. User confirmed scope across 4 questions (3 planned + 1 surfaced when GCal real-adapter gap was discovered): (1) multi-clinic + solo day one, (2) global per-clinic 15-min default buffer via `clinic_settings.transition_buffer_minutes`, (3) internal `availability_slots` + `appointments` PLUS Google Calendar two-way, (4) file `projects/google-calendar-real-adapters/` separately as N=2 DRY-formalize trigger; pilot uses `FakeCalendarAdapter` until it lands. §2 confirmed constraints written, §3a seed-first analysis filled in, §6 phases 1-4 rewritten with concrete file paths chosen to avoid collision with parallel `therapy-platform-wiring` agent (new files only; new `/api/scheduling/*` URL prefix; migration number TBD at execution time skipping wiring agent's `010`), §7 open questions added, §8 dependencies/blockers section added. **Next step:** file `projects/google-calendar-real-adapters/PROJECT.md` to close Phase 0, then await user "continue" before Phase 1. | Claude Opus 4.7 |
