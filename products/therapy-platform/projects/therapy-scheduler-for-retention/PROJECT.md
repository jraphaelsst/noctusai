# Therapy Scheduler For Retention — Project Document

> **Living document** — revise phases as work progresses.
> **Scaffolded 2026-04-22** from compliance-audit-reconciliation Phase 5 improvements bundle.
> **STATUS: PENDING USER INTERROGATION.**
> **Written for a zero-context reader.**

- **Created:** 2026-04-22
- **Last updated:** 2026-04-22
- **Status:** Filed pending interrogation. No phases designed yet.
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

_Interrogate the user before filling. Candidate questions:_
- Sweep frequency: hourly, daily, configurable?
- Should the scheduler also handle other therapy retention concerns (not just audio)?
- Deploy: any concerns running a scheduler in the therapy prod process (vs a dedicated worker)?

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

_Designed after §2 interrogation. Placeholder only._

- [ ] Phase 0 — Map the mailing/PF/erp scheduler pattern; identify the reusable bits.
- [ ] Phase 1 — Build `app/scheduler.py` + wire into `main.py`.
- [ ] Phase 2 — Tests.

---

## 7. Open questions

See §2 — all answered at interrogation time.

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
