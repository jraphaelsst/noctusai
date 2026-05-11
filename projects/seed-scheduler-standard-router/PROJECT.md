# seed-scheduler-standard-router — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION.** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer AA's PF Phase 5 close (commit `378cdf5`) flagged that PF needs a read-only "scheduled jobs view" surface (next-run / last-run / job list). N=3 adopters likely (PF + mailing + therapy). Predecessor proposal at `archive/projects/.../personal-finance-wiring/proposals/phase-5-scheduler-standard-router.md` (when archived).
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

### Phase 0 — Audit + design lock

- [ ] Read `noctusai_lib.api.scheduler.scheduler.get_jobs()` — confirm exact return shape.
- [ ] Verify Engineer AA's claim that all 3 fields (`id`, `next_run_time`, `trigger`) are surfaced.
- [ ] Decide on org-scoping: is scheduler platform-level (all jobs visible to any authed user) or org-scoped? Default rec: **platform-level for v1** (scheduler jobs are infrastructure, not user data).

### Phase 1 — Ship the router

- [ ] Author `seed/framework/backend/noctusai_seed/routers/scheduler.py`.
- [ ] Register in `_STANDARD_ROUTERS` at `routers.py:240`.
- [ ] Update `test_build_standard_routers.py::test_registry_keys_match_documented_set` drift test.
- [ ] Tests at `seed/framework/backend/tests/routers/test_scheduler.py`: happy path, empty list, auth boundary, job-not-found.

### Phase 2 — KB + close

- [ ] `KB § 03-SEED-ARCHITECTURE.md § Standard routers` — add scheduler row.
- [ ] Improvements block + §11 close.
- [ ] Archive.

### Phase 3 — Consumer wiring (deferred to per-product)

- [ ] PF opts in by adding `"scheduler"` to `standard_routers=[...]` at `app/main.py`. Recorrentes page consumes via `useSchedulerJob(jobId)`.
- [ ] Mailing/therapy opt in when their next milestone surfaces.

## 7. Open questions

- Q1: Platform-level (all authed users see all jobs) or org-scoped? **Default rec: platform-level for v1** — scheduler jobs are infra-state, not user data. If a product needs per-org filtering, file a follow-up at that trigger.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] Standard router ships + registry + drift test.
- [ ] 2 endpoints respond correctly.
- [ ] KB doc updated.

## 10. How to use this plan

Single-engineer dispatch. Mechanical seed addition.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer AA's PF P5 close surfaced N=3 forecast (PF + mailing + therapy) for a read-only scheduler-jobs surface. Standard-router shape per seed convention. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
