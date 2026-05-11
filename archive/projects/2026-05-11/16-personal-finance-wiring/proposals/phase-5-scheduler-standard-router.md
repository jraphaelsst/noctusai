# Phase 5 proposal — Seed-side `scheduler` standard router

**Project:** `personal-finance-wiring`
**Phase:** 5 (Scheduler + yfinance + AI-indicator wiring — DIVERGENT batch)
**Filed:** 2026-05-10
**Status:** DEFERRED (out-of-scope: seed/cross-product files excluded from this dispatch)
**Destination:** Cross-product project — `projects/seed-scheduler-standard-router/PROJECT.md` (to be filed by orchestrator)

---

## Context

PROJECT.md Phase 5 PF-5 calls for a new `scheduler` standard router in
`seed/framework/backend/noctusai_seed/routers.py` exposing:

- `GET /api/scheduler/jobs` — list registered jobs with `next_run`
- `GET /api/scheduler/jobs/{id}/runs` — execution history if persisted; scaffold otherwise
- `POST /api/scheduler/jobs/{id}/trigger` — manual run, `platform_admin` gated

Adopters opt in via `create_product_app(standard_routers=[..., "scheduler"])`.
PF, mailing, and therapy all consume `noctusai_lib.api.scheduler` and so are
natural N=3 adopters.

## Why deferred

Phase 1 standalone-mode note (inherited): seed/cross-product files are out of
scope for `products/personal-finance/**` dispatches. The seed change is
cross-product by definition (all three scheduler-using products would mount
the new standard router on the same factory call) — owner is a future cross-
product project, not this PF wiring sweep.

## What was shipped instead (in-scope partial)

The **UI banner sub-task** of PF-5 — the visible-in-product piece — was
shipped against existing PF data:

- `RecorrenteRow` (`products/personal-finance/frontend/src/pages/Recorrentes.tsx`)
  now renders an "Auto" badge + "Próxima execução automática: {proxima_data}"
  line on every `is_automatico=true` row, sourcing `proxima_data` directly
  from `useRecorrentes()`.
- 3 row-level unit tests (`pages/__tests__/Recorrentes.test.tsx`) cover the
  three branches: `is_automatico=true` + data, `is_automatico=false`, and
  `is_automatico=true` + missing `proxima_data`.

The "Última execução: {last_run}" indicator was NOT shipped — no
`ultima_execucao` column exists on the `recorrentes` table, and surfacing it
requires either the seed-side router OR a new migration, both downstream of
the deferred work.

## Proposed seed surface

```python
# seed/framework/backend/noctusai_seed/scheduler_router.py
from fastapi import APIRouter, Depends, HTTPException
from noctusai_lib.api import scheduler as seed_scheduler

def create_scheduler_router(deps, settings, product_name: str) -> APIRouter:
    router = APIRouter(prefix="/api/scheduler", tags=["Scheduler"])

    @router.get("/jobs")
    async def list_jobs():
        # Read from seed_scheduler.scheduler.get_jobs()
        return {"data": [
            {
                "id": j.id,
                "name": j.id,
                "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
                "trigger": str(j.trigger),
            }
            for j in seed_scheduler.scheduler.get_jobs()
        ]}

    @router.get("/jobs/{job_id}/runs")
    async def job_runs(job_id: str):
        # History scaffold — no persistence yet, return empty list.
        # Future: read from a `scheduler_runs` table the seed creates on
        # `lifespan_startup`.
        return {"data": []}

    @router.post("/jobs/{job_id}/trigger")
    async def trigger_job(job_id: str, authorization: str | None = ...):
        # platform_admin gated — read role via deps.get_user_role(user)
        # job = seed_scheduler.scheduler.get_job(job_id)
        # if not job: raise HTTPException(404, ...)
        # await job.func()
        raise NotImplementedError("Pending platform_admin gate + safe-fire impl")

    return router
```

And in `seed/framework/backend/noctusai_seed/routers.py`:

```python
_STANDARD_ROUTERS = {
    ...
    "scheduler": lambda deps, s, n, v: _create_scheduler_router(deps, s, n),
}
```

Plus the `test_build_standard_routers.py::test_registry_keys_match_documented_set`
drift-guard update + `KB § 03-SEED-ARCHITECTURE.md § Standard routers` doc.

## Adopters

| Product | Scheduler use | Standard router mount |
|---|---|---|
| `personal-finance` | `recorrentes_daily` + `recorrentes_catchup` jobs | mount via `standard_routers=[..., "scheduler"]` |
| `mailing` | (verify — uses `noctusai_lib.api.scheduler` per `seed/lib/backend/noctusai_lib/api/scheduler.py` docstring) | mount when adopted |
| `therapy-platform` | (verify per docstring) | mount when adopted |

N=3 likely — per `DRY — the recurrence rule`, this is MUST-FORMALIZE territory
once the third adopter confirms.

## Open questions for the cross-product project

1. **Run history persistence shape.** New `scheduler_runs` table in `public.` —
   or per-product table? Per-product avoids cross-schema reach; `public.` keeps
   the seed self-contained. Per the cross-schema convention surfaced in
   Phase 4 (PF-8 fix), `public.` reads via `deps.get_core_client()` is the
   canonical pattern. Default rec: `public.scheduler_runs(id, product, job_id, started_at, ended_at, status, error, summary jsonb)`.
2. **`platform_admin` gating shape.** The seed `team` standard router already
   gates on `role in ("platform_admin", "owner", "admin")`. The scheduler
   trigger is more sensitive (can fire side-effects), so `platform_admin` only
   may be too tight (no PF owner can dry-run). Suggest `("platform_admin", "owner")`.
3. **Manual trigger safety.** Coalesce + max_instances=1 in the seed
   scheduler already prevents overlapping runs, but a manual trigger should
   probably bypass the next scheduled run to avoid double-execution. Worth a
   design pass.

## How this closes when the seed project ships

- PF's `Recorrentes.tsx` banner stays — the persisted `proxima_data` from
  Phase 5 is the authoritative source. The seed router adds the optional
  "Última execução" indicator + a scheduler diagnostics page hookpoint.
- `phase-5-scheduler-standard-router.md` in this folder gets a closing line
  pointing at the cross-product project URL.
