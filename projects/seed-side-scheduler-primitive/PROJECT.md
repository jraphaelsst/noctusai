# Seed-Side Scheduler Primitive — Project Document

> **Why this project exists.** The recurrence rule fired at N=3 when therapy
> adopted its own `app/scheduler.py` (joining mailing + personal-finance).
> Per `KB § PATTERNS/project-execution.md § 2.7`, N≥3 is `MUST formalize`.
> The proper landing is a seed-side primitive `noctusai_lib.api.scheduler`
> that the 3 (soon 4 — ERP doesn't have one yet but will eventually) products
> consume, replacing the per-product `app/scheduler.py` files with one-line
> registration calls. Until that lands, therapy's `app/scheduler.py` carries
> an accept-with-rationale entry.
>
> **Filed by `projects/side-projects-batch/` Phase 1.c** as the formalization
> follow-up for the recurrence-rule trip surfaced when wiring therapy's
> audio-retention sweep. The N=2 → N=3 transition was logged in the
> Tier-1 §7 round (`projects/side-projects-batch/PROJECT.md` §11) and Q4 of
> the `therapy-scheduler-for-retention` interrogation.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** 📋 **FILED** — Phase 0 interrogation pending. No phases designed yet.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `seed-side-scheduler-primitive` (subject=seed-side-scheduler, intent=primitive)
- **Project location:** `projects/seed-side-scheduler-primitive/` (cross-product / platform-infra — lands `noctusai_lib.api.scheduler` + migrates 3 products)
- **Related docs:**
  - `products/mailing/backend/app/scheduler.py` — first instance (send-loop + scheduled campaigns + automation processor)
  - `products/personal-finance/backend/app/scheduler.py` — second instance (recurring-transaction execution)
  - `products/therapy-platform/backend/app/scheduler.py` — third instance (audio-retention sweep + generic register surface)
  - `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`
  - `KB § PATTERNS/seed-lib-layout.md` — for the layer decision (api vs domain vs primitives)
  - `KB § PATTERNS/accept-with-rationale.md` — therapy's scheduler will carry an entry until this primitive lands
  - Parent batch: `projects/side-projects-batch/PROJECT.md`

---

## 1. Context & Purpose

Three products run their own `app/scheduler.py` today:

- **Mailing** (`products/mailing/backend/app/scheduler.py`): 3 jobs — send loop (30s), scheduled campaigns (60s), automation processor (5min).
- **Personal Finance** (`products/personal-finance/backend/app/scheduler.py`): 1 job, dual triggers — daily 06:00 SP cron + 4h interval catch-up.
- **Therapy Platform** (`products/therapy-platform/backend/app/scheduler.py`): 1 job (audio-retention sweep, every `THERAPY_AUDIO_RETENTION_SWEEP_INTERVAL_HOURS` hours, default 24). Carries a generic `register(name, fn, hours=..., minutes=..., seconds=...)` surface so future therapy retention jobs slot in.

All three:
- Use `AsyncIOScheduler(timezone="America/Sao_Paulo")` from APScheduler.
- Silence APScheduler verbose DEBUG logging.
- Expose `start_scheduler()` + `stop_scheduler()` wired into `create_product_app(..., lifespan_startup=..., lifespan_shutdown=...)`.
- Use `get_admin_client()` to access the DB inside jobs (RLS-bypass needed for cross-tenant retention/sending).
- Catch + log exceptions inside each job so a bad run doesn't crash the loop.

**The shape is shared; the jobs are domain-specific.** That's a textbook seed-lib absorption candidate per `KB § GUIDES/seed-first-design.md`. The primitive should expose:
- A scheduler singleton accessor (or a `SchedulerHandle` returned per-product)
- A registration surface (interval + cron triggers)
- Lifespan wiring helpers (`start`, `stop`)
- The "silence APScheduler logging" + Sao Paulo timezone defaults
- A test-friendly interface that doesn't require a running event loop for inspection

After landing, the per-product files collapse to ~10 lines each (just the job functions + their registration calls), and the seed-side primitive owns the framework concerns.

---

## 2. Confirmed constraints

_Filled at Phase 0 interrogation. Candidate questions (recommended defaults inline; Phase 0 may revise):_

- **Layer placement** — `noctusai_lib.api.scheduler` (per the 6-layer layout, this is "framework wiring" — sits at the api layer, similar to FastAPI dep factories).
- **API shape** — singleton-per-product instance via `get_scheduler()` + module-level `register(...)` shortcut, mirroring the `noctusai_seed.app.create_product_app(...)` shape used elsewhere.
- **Interval + cron support** — both. `register(..., interval_hours=...)` for the common case + `register(..., cron="0 6 * * *")` for daily-at-06:00 patterns.
- **Logging defaults** — APScheduler silenced to WARNING by default; products opt-in to verbose logging via a kwarg.
- **Migration cadence** — one commit per product migration (mailing, PF, therapy) so each migration is bisectable; the primitive ships in its own commit ahead of the migrations.
- **Test discipline** — primitive ships with regression tests; each migration's test suite stays green at the 4,500+ test platform baseline.

---

## 3. Design principles

_Filled at Phase 0 interrogation. Provisional:_

1. **Single primitive, three migrations.** Land the seed-lib code first, then migrate one product per commit. Avoid a big-bang switch.
2. **Backwards-compatible adapter.** During migration, the primitive supports the existing `start_scheduler()` / `stop_scheduler()` shapes so `lifespan_startup` / `lifespan_shutdown` wiring doesn't change in `main.py` files.
3. **Kill the recurrence-rule trip cleanly.** After all 3 migrations land, `noctusai_scan_cross_product_helpers` should report 0 instances of the per-product scheduler pattern. Capture the before/after counts in §11.
4. **Future-product safety.** When ERP eventually grows scheduled work (e.g. financial recalculation jobs), it consumes the primitive directly — no new `app/scheduler.py` file.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES — three implementations share scheduler instance, registration surface, lifespan wiring, logging. Job *shape* (callable + interval) is identical; job *bodies* are domain-specific.
2. **Is the data source product-specific?** N/A for the primitive — each registered job carries its own DB access. The primitive is plumbing.
3. **Is the placement product-specific?** NO — scheduler lifecycle is universal across products.
4. **Is the visibility / permission rule the same?** YES — admin-client access for the job functions (RLS-bypass), product-scoped configuration via env flags.
5. **Does the seam already exist in seed?** NO — `lifespan_startup` / `lifespan_shutdown` are existing seams on `create_product_app(...)`, but the scheduler primitive itself is new.
6. **Default-on or opt-in?** OPT-IN. Products that don't need a scheduler simply don't import the primitive. Products that do, pass `lifespan_startup=scheduler.start` to `create_product_app`.

**Per-product code count after migration:** ~5-10 lines (import + register + lifespan kwargs). 0 framework code.

---

## 4. Scope

**In scope:**
- New module `seed/backend/lib/noctusai_lib/api/scheduler.py` — singleton scheduler + register surface + lifespan helpers.
- Tests at `seed/backend/lib/tests/api/test_scheduler.py`.
- KB doc at `KB § PATTERNS/scheduler-primitive.md` (or extension to `04-SHARED-LIBRARY.md`).
- Migration of 3 products: mailing, personal-finance, therapy. One commit per product migration.
- `KB § PATTERNS/accept-with-rationale.md` — clear the per-product-scheduler entry once all 3 migrations land.

**Out of scope:**
- Adding scheduling to ERP / daily-life / mailing-not-yet-shipped products (those happen organically when each grows scheduled work).
- Distributed-worker patterns (out-of-process schedulers) — that's a separate scaling project.

---

## 6. Implementation phases

### Phase 0 — Audit + interrogation

- [ ] Diff the 3 existing `app/scheduler.py` files; capture every divergence (kwarg defaults, logging, exception handling shape, etc.).
- [ ] Decide trigger surface — interval-only or interval + cron (PF uses cron).
- [ ] Decide layer placement (`api/`, `domain/scheduling/`, etc.) per KB § PATTERNS/seed-lib-layout.md.
- [ ] Run `noctusai_scan_cross_product_helpers` + `noctusai_scan_recurrence` — capture baseline counts; will be the success metric.
- [ ] Interrogate user on §2 candidate answers; lock §2 / §3 / §3a.

### Phase 1+ — Land primitive + migrate

_(designed at Phase 0)_

---

## 7. Open questions

1. **Layer placement** — `api/` vs `domain/scheduling/` vs `primitives/scheduler/`? *Recommendation:* `api/` per the 6-layer layout (framework wiring, like FastAPI dep factories).
2. **Trigger surface** — interval-only or interval + cron? *Recommendation:* both, since PF uses cron.
3. **Migration ordering** — therapy → PF → mailing (smallest job-count first), or alphabetical? *Recommendation:* therapy first (single job, simplest migration; serves as the validation), then PF (single job, cron triggers — exercises the second trigger type), then mailing (3 jobs — exercises the multi-job registration surface).

---

## 8. Dependencies & blockers

- None at filing time. The 3 per-product schedulers continue to work; this is a non-blocking optimization that pays off the recurrence-rule trip.

---

## 9. Success criteria

- `noctusai_lib.api.scheduler` lands with tests + KB doc.
- All 3 product `app/scheduler.py` files migrated to consume the primitive.
- `noctusai_scan_cross_product_helpers` baseline → 0 hits for the scheduler-pattern after migration.
- 4,500+ test platform baseline preserved across all 3 migrations.
- `KB § PATTERNS/accept-with-rationale.md` per-product-scheduler entry retired.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project filed** as the recurrence-rule formalization follow-up surfaced by `projects/side-projects-batch/` Phase 1.c (therapy-scheduler-for-retention adoption pushed N from 2 to 3). Phase 0 interrogation pending. | Claude Opus 4.7 |
