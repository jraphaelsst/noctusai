# therapy-scheduling-pilot-rollout — Project Document

> **This is a living document, not a rigid checklist.**
>
> **Write for a zero-context reader.** §1 inlines the situation; §10 commands are copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** 🅿️ **PARKED — awaiting user reactivation.** Two pilot deferrals bundled here as a single follow-up; reactivate when ready to put the scheduling pilot in front of real therapists.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `therapy-scheduling-pilot-rollout` — single-product (therapy) scope; lives at `products/therapy-platform/projects/<slug>/`. Intent `rollout` per `KB § PATTERNS/project-execution.md §8` (the pilot code is shipped; this project lands the production-readiness pieces).
- **Related docs:**
  - `products/therapy-platform/projects/therapy-scheduling-pilot/PROJECT.md` — predecessor; ships the engine wiring, GCal credential resolver, OAuth shape, and frontend page. Closed 2026-05-03.
  - `products/therapy-platform/backend/migrations/011_scheduling_pilot.sql` — the production schema this project will exercise live.
  - `products/therapy-platform/backend/app/routers/scheduling.py` — the OAuth-callback endpoint that needs a registered Google client.
  - `products/therapy-platform/frontend/src/pages/therapist/Scheduling.tsx` — the page that needs a route + nav entry to be reachable.
  - `seed/lib/backend/noctusai_lib/integrations/google_calendar/` — the real `GoogleCalendarOAuthAdapter` + `update_event` Protocol method (added 2026-05-03 as a pilot follow-up improvement).

---

## 1. Context & Purpose

The `therapy-scheduling-pilot` shipped end-to-end on 2026-05-03 with the engine wiring, custom `ProfessionalAvailabilityConflict`, internal-DB + Google Calendar two-way sync, encrypted OAuth refresh-token storage (pgcrypto + Vault, 7-day re-auth), the `/api/scheduling/*` REST surface (5 endpoints incl. OAuth `authorize`/`callback`), the therapist-facing slot-picker page, and 38 tests across backend + frontend.

Two pieces are explicitly NOT shipped because they require human/infra action that an agent session cannot complete alone:

1. **Production OAuth credentials are not configured.** `THERAPY_GOOGLE_CLIENT_ID` and `THERAPY_GOOGLE_CLIENT_SECRET` are present in `app/config.py` but unset in any deployed env. Until a Google Cloud Console OAuth client exists and its redirect URI matches the frontend origin, the `/api/scheduling/gcal/callback` flow returns a 500 (helper-detected: `_resolver` returns `None` → factory falls back to `FakeCalendarAdapter` which is the right safe default for missing-credentials, but means therapists cannot actually connect their real calendars).
2. **The Scheduling page is not on the therapist nav / route table.** `Scheduling.tsx` exists at `frontend/src/pages/therapist/Scheduling.tsx` and is fully wired through `useScheduling.ts`, but no `<Route>` references it and no nav entry links to it. Reason: at pilot-close time the parallel `therapy-platform-wiring` agent had not yet published its Phase 0 gap-table, so the safe move was to add net-new files only and defer route/nav touches to avoid collision.

The win: a therapist logs in, sees a "Agendamento" link in their nav, clicks it, sees their available slots (filtered by their availability + GCal events), connects their Google Calendar via real OAuth, and books a real session that lands as both a `therapy.appointments` row AND a Google Calendar event in their connected calendar.

---

## 2. Confirmed constraints

Decisions captured at scaffold time. Re-interrogate at reactivation if the world has shifted.

- **Bundle both deferrals as one project, not two.** *(Per user instruction at pilot close.)* Reasoning: each deferral is small on its own; two separate projects would over-process the work. They share a context (the pilot's productionization) and will be executed in the same session.
- **Manual QA cannot be agent-driven.** Setting up the Google Cloud Console OAuth client, registering the redirect URI, copying credentials into `.env`, then doing a real connect-and-book flow is human work. The project's role is to (a) document the exact steps, (b) ship any code adjustments the live test surfaces (likely small).
- **Route + nav placement TBD at reactivation** — depends on the therapy-platform-wiring agent's Phase 0 gap-table state at the time. If wiring has shipped therapist nav by then, slot in alongside the existing entries. If wiring is still pre-Phase-0 or the nav touch hasn't landed, coordinate to avoid collision.

---

## 3. Design principles

1. **Smallest blast radius.** Don't refactor the pilot during rollout. The pilot's surfaces are stable; this project layers on production credentials + reachability only.
2. **Verify the seed ships it (still applies).** Before assuming any helper exists, check current state — the GCal adapters and `update_event` were added by other projects post-pilot; more may have shipped by the time this reactivates.
3. **AST-first** for any code edits to `App.tsx` / route tables / nav config (per `feedback_ast_first`).

---

## 3a. Seed-first analysis

Required even for single-product scope (`feedback_seed_first_at_authoring_time`).

1. **Contract identical for every product?** Partially. The Google OAuth Console setup is per-product (each product has its own client) but the *steps* are identical — could be promoted to a runbook in `KB § GUIDES/` if a third product needs OAuth.
2. **Data source product-specific?** YES — the credentials live in `therapy.therapist_profiles.gcal_*` (encrypted via the migration-011 helpers).
3. **Placement product-specific?** YES — the route + nav additions are entirely in `products/therapy-platform/frontend/`.
4. **Visibility / permission?** Therapist-only flow. Existing RLS + role guards cover.
5. **Seam exists in seed?** YES for the OAuth adapter + update_event; the consumer wiring is product-specific.
6. **Default-on or opt-in?** Opt-in (therapist must connect; no auto-mount).

**Per-product code count this project requires:** ~2 file edits (`App.tsx` route, nav config) + 1 docs file (the OAuth setup runbook). Zero seed touches expected.

---

## 4. Scope

**In scope:**
- `KB § GUIDES/` — write a copy-paste runbook for the Google Cloud Console OAuth client setup (project creation, OAuth consent screen, credentials, scopes, redirect URI). Reusable for any future product that adopts user-delegated GCal.
- Add `THERAPY_GOOGLE_CLIENT_ID` / `THERAPY_GOOGLE_CLIENT_SECRET` to the deployed env (manual; document in the runbook how + where).
- Live OAuth round-trip: connect a real Google account, verify `gcal_authorized_at` populates + `gcal_refresh_token_encrypted` round-trips through `therapy.encrypt_gcal_token` / `decrypt_gcal_token`.
- Live booking: book a real session from the UI; verify event appears in the therapist's connected calendar; manually add an event in GCal; verify slot generator excludes the window on next `/api/scheduling/candidates` call.
- Live re-auth: artificially push `gcal_authorized_at` to >7 days ago via SQL; verify the UI prompts re-OAuth.
- Frontend `App.tsx` route addition for `/therapist/agendamento` (or whatever path the wiring agent's nav consensus settles on).
- Therapist nav addition (link + icon).
- Any small fixes the live flow surfaces (likely: error-message polish on the OAuth-callback failure paths, friendly empty-state on no-slots, etc.).

**Out of scope:**
- Patient self-booking (deferred to its own project per pilot §7 Q2).
- Service-account adapter wiring for clinic-owned calendars (separate use case from per-therapist OAuth; ship if/when a clinic asks).
- Production rate-limiting / throttling on the OAuth endpoints (defer until evidence of abuse).
- LiveKit / video-room integration with the booked appointment (separate concern).
- `update_event`-triggered notification UX changes (the seed adapter sends `sendUpdates=all` already; if the UX needs more, file separately).

---

## 5. Architecture / Data Model

No new tables, columns, or migrations. All schema work shipped with the pilot's migration 011.

The runbook in scope adds **one new doc** at `KB § GUIDES/google-oauth-setup.md` (proposed slug — confirm at execution time per `KB § INDEX.md`).

---

## 6. Implementation phases (sketch — refine at reactivation)

### Phase 0 — State audit at reactivation

- [ ] Verify pilot still passes: `pytest products/therapy-platform/backend/tests/services/test_scheduling_*.py tests/routers/test_scheduling_router.py -q` should be 34/34.
- [ ] Verify seed still passes: `pytest seed/lib/backend/tests/integrations/google_calendar/ -q` should be 32/32 (or higher if more landed).
- [ ] Verify the route + nav landscape: read `frontend/src/App.tsx` and the therapy-wiring project's gap-table (if published) to pick the right insertion point without collision.
- [ ] Confirm GCal real-adapter project is still closed and the `update_event` Protocol method is still present.

### Phase 1 — OAuth credentials runbook + env wiring

- [ ] Write `KB § GUIDES/google-oauth-setup.md` — copy-paste steps for Google Cloud Console OAuth client creation. Include: project creation, OAuth consent screen (External), Calendar API enablement, OAuth client ID (Web application), redirect URI registration, scopes (`.../auth/calendar`), credentials JSON download.
- [ ] Document the env-var placement (`THERAPY_GOOGLE_CLIENT_ID`, `THERAPY_GOOGLE_CLIENT_SECRET`) for both local dev (`.env` at repo root) and prod deploy (Render / wherever).
- [ ] Add the doc to `KB § INDEX.md`.

### Phase 2 — Frontend route + nav

- [ ] Add `<Route path="/therapist/agendamento" element={<Scheduling />} />` (path TBD) to `App.tsx`. Use AST tooling (`ts-morph`) for the import + JSX additions.
- [ ] Add nav entry — link + icon — at the right spot in the therapist nav config. Mirror the established nav-pattern (probably `useTherapistNav` or similar).
- [ ] Cross-reference the wiring agent's Phase 0 gap-table to confirm zero collision.
- [ ] `npx vite build` clean.

### Phase 3 — Live OAuth + booking + re-auth QA

- [ ] User completes the runbook to spin up a real Google OAuth client; confirms env vars are set.
- [ ] Live connect: navigate to `/therapist/agendamento`, click "Conectar Google Calendar", complete the consent flow, verify the redirect lands on `/therapist/scheduling/gcal-callback` and the `connected: true` response shows.
- [ ] Verify DB state: `select gcal_authorized_at, length(gcal_refresh_token_encrypted) from therapy.therapist_profiles where user_id = ...;` — both columns populated.
- [ ] Live book: select a slot, enter a patient_id, click "Confirmar agendamento". Verify (a) `therapy.appointments` row inserted with `status='waiting'` + `google_event_id` set, (b) the event appears in the therapist's connected calendar.
- [ ] Live blackout: manually add a 1-hour event in the connected calendar, refresh `/candidates`, confirm the slot generator excludes the window.
- [ ] Live re-auth: `update therapy.therapist_profiles set gcal_authorized_at = now() - interval '8 days' where user_id = ...;` + reload page; confirm the re-auth banner appears and the connect flow restarts.
- [ ] Live reschedule: PATCH an appointment to a new slot; verify the GCal event MOVES (same event_id, new times) instead of being recreated.

### Phase 4 — Polish + close

- [ ] Capture any UX fixes the live flow surfaced; apply inline (apply-inline-then-delete proposals methodology).
- [ ] Final pytest + vite build.
- [ ] Project close — final commit + `git push`; folder delete.

---

## 7. Open questions

1. **Route path slug — `/therapist/agendamento` or `/therapist/scheduling`?** *(Phase 2.)* Recommendation: `/therapist/agendamento` to match the existing PT-BR convention (e.g. `/admin/agendamentos` from the wiring project, `Calendar.tsx` is the existing therapist-side page). Decided by: Claude during Phase 2, user can override.
2. **Should the new page replace, sibling, or extend the existing `Calendar.tsx`?** *(Phase 2.)* Recommendation: SIBLING for now (different concern — Calendar.tsx is event viewing, Scheduling.tsx is slot picking + booking); merge later if a UX convergence is requested. Decided by: Claude during Phase 2, user can override.
3. **OAuth consent screen branding** — what app name / logo / privacy URL goes on Google's consent screen? *(Phase 1.)* Decided by: user.
4. **Test-mode users vs production verification** — initial Google OAuth clients require explicit test users until the app passes Google's verification. Acceptable scope for pilot rollout? *(Phase 1.)* Recommendation: yes — pilot stays in test-mode; production verification is a separate effort with Google.

---

## 8. Dependencies & blockers

- **GCal real adapters** — already shipped (`projects/google-calendar-real-adapters/` closed 2026-05-03). No blocker.
- **`update_event` Protocol method** — added 2026-05-03 as a pilot-close improvement (this project's predecessor session). No blocker.
- **`therapy-platform-wiring` Phase 6 (therapist portal)** — may or may not have landed nav touches by reactivation time. If overlap, coordinate per `feedback_parallel_agent_collision_protocol`.
- **User availability for live QA** — Phase 3 cannot proceed without the user running the OAuth flow on a real Google account.

---

## 9. Success criteria

- A therapist can navigate to the Scheduling page from the nav (no URL hand-typing required).
- The "Conectar Google Calendar" flow completes end-to-end with a real Google account.
- A booked session appears in the therapist's real Google Calendar with the right times.
- Off-platform GCal events block the slot generator on the next candidates call.
- Re-auth banner appears at the 7-day mark and the connect flow restarts cleanly.
- Reschedule moves the GCal event in-place (same event_id, new times).
- `npx vite build` clean; `pytest products/therapy-platform/backend/tests/` green.
- KB sync: `bash scripts/verify-kb-sync.sh` clean after the runbook lands.

---

## 10. How to use this project

- Currently parked. Reactivate when ready to put scheduling in front of real therapists.
- At reactivation: re-interrogate user on §7 questions; refine §6 with concrete file paths (informed by current `App.tsx` state); flip status to "Phase 0 in progress".
- Verification commands:

```bash
# Pilot regression check
cd products/therapy-platform/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest \
    tests/services/test_scheduling_service.py \
    tests/services/test_scheduling_conflicts.py \
    tests/routers/test_scheduling_router.py -q

# Seed regression
cd seed/lib/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest \
    tests/integrations/google_calendar/ -q

# Frontend
cd products/therapy-platform/frontend && npx vitest run src/hooks/__tests__/useScheduling.test.ts
cd products/therapy-platform/frontend && npx vite build
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project scaffolded** at `therapy-scheduling-pilot` close — bundles two deferrals (manual GCal QA setup + frontend routing/nav additions) into one follow-up per user instruction. Status: PARKED, awaits reactivation when therapist-facing rollout is wanted. Pilot's three improvements (`update_event` to seed Protocol, `updated_payloads` to MockSupabaseClient, in-place reschedule refactor) were applied inline before this scaffold and are validated by 34 pilot tests + 32 seed calendar tests + 7 mock-tracking tests, all green. | Claude Opus 4.7 |
