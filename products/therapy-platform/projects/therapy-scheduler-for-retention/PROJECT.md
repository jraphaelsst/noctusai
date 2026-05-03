# Therapy Scheduler For Retention — Project Document

> **Living document** — revise phases as work progresses.
> **Scaffolded 2026-04-22** from compliance-audit-reconciliation Phase 5 improvements bundle.
> **STATUS: PENDING USER INTERROGATION.**
> **Written for a zero-context reader.**

- **Created:** 2026-04-22
- **Last updated:** 2026-05-03
- **Status:** ⏳ Interrogation closed 2026-05-03 (Tier 1 round of `projects/side-projects-batch/`). Q3=daily configurable, Q4=audio-only v1 with generic-shape registration, Q5=in-process behind flag. **Recurrence-rule trip captured** (mailing/PF/erp/therapy = N=4 schedulers) — follow-up `seed-side-scheduler-primitive` project filed in §11. Phase 0 ready.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Related docs:**
  - `products/therapy-platform/backend/app/services/audio_retention_service.py` — exposes `run_retention_sweep(db)` callable.
  - `products/therapy-platform/backend/app/routers/lgpd.py` — existing manual admin endpoint `POST /api/lgpd/run-audio-retention`.
  - `products/mailing/backend/app/main.py` — reference for `lifespan_startup` / `lifespan_shutdown` scheduler pattern.
  - `products/personal-finance/backend/app/main.py` — same.
  - `products/erp-imobiliario/backend/app/main.py` — same.
  - `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md` § Named seams — `lifespan_startup` + `lifespan_shutdown` are documented seams on `create_product_app()`.
- **Project slug:** `therapy-scheduler-for-retention`
- **Project location:** `products/therapy-platform/projects/therapy-scheduler-for-retention/` (single-product scope)

---

## 1. Context & Purpose

compliance-audit-reconciliation Phase 5 (2026-04-22) shipped `audio_retention_service.run_retention_sweep(db)` — physically deletes session audio past `download_expires_at`. Invokable via admin endpoint for now.

**Gap:** therapy has no scheduler today (`app/main.py` has no `lifespan_startup`/`lifespan_shutdown`). Mailing, Personal Finance, and ERP each boot an APScheduler-like loop via those seed hooks. Therapy needs to match.

This project wires a scheduler into therapy + has it call `run_retention_sweep` hourly.

---

## 2. Confirmed constraints

Answers locked 2026-05-03 in the Tier-1 §7 round of `projects/side-projects-batch/` Phase 1.a.

- **Sweep frequency** — **daily, env-configurable** via `THERAPY_AUDIO_RETENTION_SWEEP_INTERVAL_HOURS` (default `24`). *(Q3 answered: hourly is overkill for a retention timescale measured in days+; daily matches the cadence of `download_expires_at` boundaries; env-configurable so dev/staging can dial down to minutes for testing.)*
- **Scheduler scope** — **audio-only for v1**, but `app/scheduler.py` built with a generic registration surface (`scheduler.register(name, fn, interval)`) so future therapy retention jobs (e.g. transcription cleanup, journal archive) slot in without re-architecting. *(Q4 answered: don't widen scope now, but design the API for future retention jobs.)*
- **Deploy shape** — **in-process** (alongside FastAPI), behind a `THERAPY_SCHEDULER_ENABLED` flag (default `true` in prod, `false` in CI/test). *(Q5 answered: matches mailing/PF/erp; consistency wins; dedicated-worker deployment is a future scaling decision, not v1.)*
- **N=4 recurrence-rule trip — accepted with rationale, follow-up project filed.** Adding therapy as the 4th per-product scheduler triggers the recurrence rule's `MUST formalize` action. The proper landing is a seed-side `noctusai_lib.api.scheduler` primitive that all 4 products consume. **For this child:** ship therapy's scheduler matching the mailing/PF/erp pattern (so the 4th product isn't blocked on the formalization). **In parallel:** file `projects/seed-side-scheduler-primitive/` as the formalization follow-up; once landed, all 4 products migrate to consume it. *(`KB § PATTERNS/accept-with-rationale.md` entry: "Per-product scheduler.py at N=4 — accept while seed-side primitive is staged; revisit on primitive landing.")*

---

## 3. Design principles

1. **Reuse the mailing/PF/erp pattern** — don't invent. `lifespan_startup`/`lifespan_shutdown` are existing named seams.
2. **Idempotent** — the sweep is already idempotent (per Phase 5 design); scheduler re-runs safely.
3. **Dev/CI-safe** — must not fire in test runs (would delete real Supabase Storage objects if pointed at live DB).

---

## 4. Scope

**In scope:**
- `lifespan_startup` + `lifespan_shutdown` wiring on `products/therapy-platform/backend/app/main.py`.
- Scheduler config (interval, logging).
- Tests that verify the scheduler starts + stops (no live sweep in tests).

**Out of scope:**
- Other therapy jobs (appointment reminders, payment reconciliation, etc.) — if they come up, file separately.
- Platform-wide scheduler abstraction (already handled per-product via the seam).

---

## 5. Architecture / Data Model

No schema changes. Pure runtime wiring via the existing `create_product_app(..., lifespan_startup=..., lifespan_shutdown=...)` seam.

### Files in scope

- `products/therapy-platform/backend/app/main.py` — add lifespan kwargs.
- `products/therapy-platform/backend/app/scheduler.py` — new file (mirror `products/mailing/backend/app/scheduler.py` structure).
- Tests: `tests/test_scheduler.py` or equivalent.

---

## 6. Implementation phases

### Phase 0 — Map the existing 3 schedulers

- [ ] Read `products/mailing/backend/app/scheduler.py` (and `main.py` lifespan wiring).
- [ ] Read `products/personal-finance/backend/app/scheduler.py` (and `main.py`).
- [ ] Read `products/erp-imobiliario/backend/app/scheduler.py` (and `main.py`).
- [ ] Diff the three: where do they share shape (`register`/`start`/`shutdown` API, env-flag check, log structure), and where do they diverge (job set, intervals, error handling)?
- [ ] Capture findings as a recurrence inventory in §11 — feeds the parallel `seed-side-scheduler-primitive` follow-up project.
- [ ] Run `noctusai_scan_recurrence` against `products/*/backend/app/scheduler.py` to confirm N=3 baseline measurement.

### Phase 1 — Build `therapy-platform/backend/app/scheduler.py` + wire

- [ ] Mirror the cleanest of the 3 existing patterns (decision driven by Phase 0 diff). Use the SAME structure so the future migration to `noctusai_lib.api.scheduler` is a one-shot.
- [ ] Generic `register(name, fn, interval)` surface (Q4 design).
- [ ] Env vars: `THERAPY_SCHEDULER_ENABLED` (default `true`), `THERAPY_AUDIO_RETENTION_SWEEP_INTERVAL_HOURS` (default `24`).
- [ ] Wire `audio_retention_service.run_retention_sweep` as the only registered job in v1.
- [ ] Add `lifespan_startup` + `lifespan_shutdown` to `app/main.py`'s `create_product_app(...)` call.
- [ ] Use AST-first edits (libcst) for `main.py` modification.

### Phase 2 — Tests + verification

- [ ] Unit test: `scheduler.register(...)` adds to internal registry, `start()` schedules, `shutdown()` stops cleanly.
- [ ] Integration test: with `THERAPY_SCHEDULER_ENABLED=false` (test default), no jobs fire even at startup. With it `true` and a 1-second test interval, the test job fires.
- [ ] Logging: scheduler start + shutdown events at INFO; per-job invocation at DEBUG.
- [ ] CI safety: confirm `pytest` runs do NOT trigger live `audio_retention_service.run_retention_sweep` (env flag default + test bootstrap).
- [ ] Run therapy backend pytest: `cd products/therapy-platform/backend && /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q`.
- [ ] Phase-end keeper review: `python mcp/noctusai/cli.py --review`.

### Phase 3 — File the follow-up

- [ ] Scaffold `projects/seed-side-scheduler-primitive/PROJECT.md` from `templates/PROJECT-TEMPLATE.md`. §1 captures the N=4 recurrence trip; §6 phases formalize `noctusai_lib.api.scheduler` + migrate all 4 products.
- [ ] Mark this child's accept-with-rationale entry in `KB § PATTERNS/accept-with-rationale.md`: "Per-product scheduler.py at N=4 — accept; revisit on `seed-side-scheduler-primitive` landing."

---

## 7. Open questions

All §7 questions resolved 2026-05-03 (Tier 1 round of `projects/side-projects-batch/` Phase 1.a). See §2 for answers + reasoning.

- Q3 (sweep frequency) — ✅ ANSWERED: daily, env-configurable.
- Q4 (scheduler scope) — ✅ ANSWERED: audio-only v1 with generic registration surface.
- Q5 (deploy shape) — ✅ ANSWERED: in-process behind flag.
- **N=4 recurrence-rule trip** — ✅ TRIAGED: accept-with-rationale + follow-up project filed (Phase 3).

---

## 8. Dependencies & blockers

- User interrogation (§2 questions).
- Low risk — additive change.

---

## 9. Success criteria

- Therapy pytest baseline preserved (1131 passing as of 2026-04-22).
- Scheduler start + stop events logged at boot.
- `run_retention_sweep` invocation traceable in logs.

---

## 10. How to use this project

Interrogate, then phase-by-phase.

### Verification commands

```bash
cd products/therapy-platform/backend && /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-22 | **Initial scaffold** — filed as Phase 5 follow-up from compliance-audit-reconciliation. Pending interrogation. | Claude Opus 4.7 |
| 2026-05-03 | **§7 round closed.** Q3=daily/env-configurable, Q4=audio-only v1 with generic-shape registration, Q5=in-process behind `THERAPY_SCHEDULER_ENABLED` flag. **Recurrence-rule trip flagged**: per-product scheduler at N=4 (mailing/PF/erp/therapy) — triaged accept-with-rationale + follow-up `seed-side-scheduler-primitive` project to be filed at Phase 3. §2 + §3 + §6 phase plan filled. Phase 0 ready to execute as part of `projects/side-projects-batch/` Phase 1.c. | Claude Opus 4.7 |
