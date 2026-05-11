# seed-scheduler-standard-router — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** ✅ **CLOSED — Phases 0/1/2 shipped.** Read-only `scheduler` standard router lives at `seed/framework/backend/noctusai_seed/scheduler_router.py`; registered in `_STANDARD_ROUTERS`; 11/11 tests green; KB updated. Phase 3 (per-product consumer wiring) is per-product opt-in and out of scope here.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `seed-scheduler-standard-router`
- **Related docs:**
  - Engineer AA's proposal: `products/personal-finance/projects/personal-finance-wiring/proposals/phase-5-scheduler-standard-router.md`
  - `seed/lib/backend/noctusai_lib/api/scheduler/scheduler.py` — exposes `get_jobs()` with `id` + `next_run_time` + `trigger`
  - `seed/framework/backend/noctusai_seed/routers.py` — `_STANDARD_ROUTERS` registry

---

## 1. Context & Purpose

PF's Recorrentes page wants to display "next automatic execution" + "last execution" per recurring row. The data already exists on `noctusai_lib.api.scheduler.scheduler.get_jobs()` — `id` + `next_run_time` + `trigger` are returned per Job. No new persistence needed for the read path.

Three products likely need this same read surface:
- **PF**: Recorrentes page (immediate consumer).
- **Mailing**: scheduled campaigns / sends.
- **Therapy**: scheduled re-auth checks, refresh tokens, batch jobs.

**N=3 forecast** → ship as a standard router from day one. Per-product implementations would compound to 3× the surface.

## 2. Confirmed constraints

- **Read-only standard router** — `/api/scheduler/jobs` GET + `/api/scheduler/jobs/{id}` GET.
- **Already has the data path** — `scheduler.get_jobs()` returns what's needed.
- **`ultima_execucao` requires a `scheduler_runs` table** OR per-job persistence — out of scope for this read-only router; defer to a sibling write path if needed.
- **Standard router registry** — add to `_STANDARD_ROUTERS` in `seed/framework/backend/noctusai_seed/routers.py:240`.

## 3. Design principles

1. **Read-only first.** Write (cancel-job, manual-run) deferred until a second product asks.
2. **Standard router shape.** Auth via `Depends(get_current_user_org)`; org-scoping at the controller (or accept-with-rationale if scheduler jobs are platform-level).
3. **Response DTO at boundary.** Don't leak APScheduler internals; emit `{id, next_run_time, trigger_kind, trigger_args, status}`.

## 3a. Seed-first analysis

- **Cross-product?** YES — N=3 forecast.
- **Seed home?** `seed/framework/backend/noctusai_seed/routers/scheduler.py` + register in `_STANDARD_ROUTERS`.
- **Per-product code count?** 0 — products opt in by listing `"scheduler"` in `standard_routers=[...]` at `create_product_app(...)`.

## 4. Scope

- **In scope:**
  - New standard router `scheduler` in seed framework.
  - 2 endpoints (GET `/api/scheduler/jobs`, GET `/api/scheduler/jobs/{id}`).
  - Response DTO + Pydantic schemas.
  - Tests (router + boundary + auth).
  - Registry entry + drift test update.
  - KB doc entry under `KB § 03-SEED-ARCHITECTURE.md § Standard routers`.

- **Out of scope:**
  - Write paths (cancel-job, trigger-now).
  - `ultima_execucao` persistence (no `scheduler_runs` table here).
  - Per-product wiring (each product opts in later).

## 5. Architecture / Data Model

```python
# seed/framework/backend/noctusai_seed/routers/scheduler.py
from fastapi import APIRouter, Depends
from noctusai_lib.api.scheduler import scheduler

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

class SchedulerJobDTO(BaseModel):
    id: str
    next_run_time: datetime | None
    trigger_kind: str  # 'cron', 'interval', 'date'
    trigger_args: dict[str, Any]

@router.get("/jobs", response_model=list[SchedulerJobDTO])
async def list_jobs(_: UserOrg = Depends(get_current_user_org)) -> list[SchedulerJobDTO]: ...

@router.get("/jobs/{job_id}", response_model=SchedulerJobDTO)
async def get_job(job_id: str, _: UserOrg = Depends(get_current_user_org)) -> SchedulerJobDTO: ...
```

## 6. Implementation phases

### Phase 0 — Audit + design lock ✅

- [x] Read `noctusai_lib.api.scheduler.scheduler.get_jobs()` — confirm exact return shape. _(Found at `seed/lib/backend/noctusai_lib/api/scheduler.py` — NOT `api/scheduler/scheduler.py` as the spec said. `get_jobs()` returns `list[apscheduler.job.Job]`; each Job has `id`, `trigger`, and a `next_run_time` slot. **Slip captured**: `next_run_time` is in `Job.__slots__` but APScheduler only assigns it when the scheduler is started — pre-start jobs raise `AttributeError` on access. DTO uses `getattr(job, "next_run_time", None)` to surface canonical None for "not yet scheduled".)_
- [x] Verify Engineer AA's claim that all 3 fields (`id`, `next_run_time`, `trigger`) are surfaced. _(Confirmed — Engineer AA correct. Caveat above re. pre-start `next_run_time`.)_
- [x] Decide on org-scoping: is scheduler platform-level (all jobs visible to any authed user) or org-scoped? **Decision: platform-level for v1** per Q1 default rec. Scheduler jobs are infrastructure state, not user data. Auth still required (`deps.get_current_user`) but no per-org filter applied. If a product needs per-org filtering, file a follow-up.

**Improvements (Phase 0):**
- The PROJECT.md spec at line 12 said `seed/lib/backend/noctusai_lib/api/scheduler/scheduler.py` — the actual path is `seed/lib/backend/noctusai_lib/api/scheduler.py` (no nested `scheduler/` subdir). Minor doc slip from Engineer AA's filing; not a blocker.
- The PROJECT.md spec at §5 said "author `seed/framework/backend/noctusai_seed/routers/scheduler.py`" but the existing seed convention is flat modules (`ai_router.py`, `ai_feedback_router.py`, `llm_router.py`), not a `routers/` subpackage. Authored at `seed/framework/backend/noctusai_seed/scheduler_router.py` to mirror siblings.

### Phase 1 — Ship the router ✅

- [x] Author `seed/framework/backend/noctusai_seed/scheduler_router.py`. _(177 lines — DTO + trigger-serialization helper + factory. Mirrors `ai_feedback_router.py` / `ai_router.py` shape.)_
- [x] Register in `_STANDARD_ROUTERS` at `routers.py`. _(Added `"scheduler": _build_scheduler_router` with deferred import — keeps APScheduler off the hot path for products that don't run background jobs. Module docstring updated to list 7 bundled routers.)_
- [x] Update `test_build_standard_routers.py::test_registry_keys_match_documented_set` drift test. _(`_ALL_NAMES` extended with `"scheduler"`. Drift test green.)_
- [x] Tests at `seed/framework/backend/tests/routers/test_scheduler.py`. _(11 tests across 4 classes: `TestListJobsEndpoint` (3), `TestGetJobEndpoint` (3), `TestAuthBoundary` (3), `TestRegistryWiring` (2). All assert `.status_code` per status-code-assertion rule. Seed real APScheduler jobs via the public `register(...)` API — no monkey-patching of our own code. Patches limited to `deps.get_current_user` (auth boundary / external integration).)_

**Improvements (Phase 1):**
- **Module-level singleton + reset slip**. `noctusai_lib.api.scheduler.reset_for_testing()` rebinds the module-level `scheduler` variable. A `from noctusai_lib.api.scheduler import scheduler` snapshot in the router would go stale after the first reset, exercising a detached AsyncIOScheduler instance silently. Captured in router via `from noctusai_lib.api import scheduler as scheduler_module` + `scheduler_module.scheduler.get_jobs()` at call time — tracks rebound singleton correctly. Pattern worth surfacing for any future router that consumes a `reset_for_testing()`-style primitive.
- **Trigger serialization is type-aware via class name, not `isinstance`**. Decouples the router from APScheduler import surface at collection time and gracefully handles custom trigger subclasses (fall through to class-name + empty args).

### Phase 2 — KB + close ✅

- [x] `KB § 03-SEED-ARCHITECTURE.md § Standard routers` — add scheduler row. _(Added a full 7-row table covering every bundled router with endpoints / auth / backing storage. The inline registry-key lists at lines 165 and 177 + the seams-table at line 481 also got the new key. Sync hook green.)_
- [x] Improvements block + §11 close. _(This block; §11 entry below.)_
- [ ] Archive. _(Orchestrator handles archive per brief.)_

### Phase 3 — Consumer wiring (deferred to per-product) — out of scope here

- [ ] PF opts in by adding `"scheduler"` to `standard_routers=[...]` at `app/main.py`. Recorrentes page consumes via `useSchedulerJob(jobId)`. _(per-product opt-in)_
- [ ] Mailing/therapy opt in when their next milestone surfaces. _(per-product opt-in)_

## 7. Open questions

- Q1: Platform-level (all authed users see all jobs) or org-scoped? **Default rec: platform-level for v1** — scheduler jobs are infra-state, not user data. If a product needs per-org filtering, file a follow-up at that trigger.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [x] Standard router ships + registry + drift test. _(`scheduler_router.py` + `_STANDARD_ROUTERS["scheduler"]` + drift test extended; 48/48 framework tests green.)_
- [x] 2 endpoints respond correctly. _(GET `/api/scheduler/jobs` + GET `/api/scheduler/jobs/{job_id}`; 11/11 router tests green including auth boundary, empty list, happy path, job-not-found.)_
- [x] KB doc updated. _(`KB § 03-SEED-ARCHITECTURE.md` — 7-row Standard routers table added; registry-key lists synced; verify-kb-sync.sh green.)_

## 10. How to use this plan

Single-engineer dispatch. Mechanical seed addition.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer AA's PF P5 close surfaced N=3 forecast (PF + mailing + therapy) for a read-only scheduler-jobs surface. Standard-router shape per seed convention. | claude-opus-4-7 |
| 2026-05-10 | **Phase 0/1/2 shipped + closed.** Author `noctusai_seed/scheduler_router.py` (177 LoC) with `SchedulerJobDTO` + type-aware trigger serializer (cron / interval / date / class-name fallback). Register `"scheduler"` in `_STANDARD_ROUTERS` with deferred-import factory. Drift test extended. 11 router tests across happy/empty/auth-boundary/not-found. KB Standard routers table added (7 routers, full contracts). 2 design slips captured in Improvements blocks: (a) PROJECT.md spec used wrong file path for the seed-lib scheduler module (`api/scheduler/scheduler.py` vs actual `api/scheduler.py`); (b) `noctusai_lib.api.scheduler.reset_for_testing()` rebinds the module-level `scheduler` variable → routers must import-the-module, not import-the-symbol, to track the rebound singleton. Engineer findings returned as text per the §17.6 return-as-text protocol. | engineer (worktree-agent-ad355bb012873d8f0) |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
