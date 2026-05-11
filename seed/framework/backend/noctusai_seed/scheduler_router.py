"""
Shared scheduler-jobs router — `/api/scheduler` read-only surface for every
product that opts in.

Endpoints:
    GET /api/scheduler/jobs              → list[SchedulerJobDTO]
    GET /api/scheduler/jobs/{job_id}     → SchedulerJobDTO

Backing data: ``noctusai_lib.api.scheduler.scheduler.get_jobs()`` — the
APScheduler `AsyncIOScheduler` singleton instantiated by the
`noctusai_lib.api.scheduler` primitive. Read-only: write paths
(cancel-job, trigger-now) are deferred until a second consumer surfaces.

Auth: any authenticated user (`Depends(deps.get_current_user)`-shaped).
Scheduler jobs are *infrastructure state*, not user data — v1 is
platform-level (no per-org filtering). If a product needs per-org
filtering, file a follow-up; see ``KB § PATTERNS/accept-with-rationale.md``.

DTO contract — `SchedulerJobDTO`:
    - id: job id (registered via `noctusai_lib.api.scheduler.register(name, ...)`)
    - next_run_time: next scheduled run (ISO 8601) or `None` if paused
    - trigger_kind: one of `"cron"`, `"interval"`, `"date"`, or class-name
      fallback for unrecognized triggers
    - trigger_args: type-specific trigger config — for `"cron"` the
      non-wildcard field names + values; for `"interval"` the
      `{"seconds": <total>}` interval

Products opt in via ``create_product_app(standard_routers=["scheduler", ...])``.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

# Import the module — NOT the `scheduler` symbol directly. The seed lib's
# `reset_for_testing()` rebinds the module-level `scheduler` variable
# (clean slate between tests), so a `from ... import scheduler` snapshot
# would go stale after the first reset and silently exercise a detached
# AsyncIOScheduler instance. Routing through `scheduler_module.scheduler`
# at call time tracks the rebound singleton correctly.
from noctusai_lib.api import scheduler as scheduler_module

logger = logging.getLogger(__name__)


class SchedulerJobDTO(BaseModel):
    """Boundary DTO for an APScheduler job — leaks none of APScheduler's
    internal types (Job / BaseTrigger) to consumers."""

    id: str = Field(..., description="Job id (set via noctusai_lib.api.scheduler.register).")
    next_run_time: Optional[datetime] = Field(
        default=None,
        description="Next scheduled run, or null when the job is paused.",
    )
    trigger_kind: str = Field(
        ...,
        description="Trigger flavor: 'cron', 'interval', 'date', or class-name fallback.",
    )
    trigger_args: dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific trigger config (non-wildcard cron fields, interval seconds, etc.).",
    )


def _serialize_trigger(trigger: Any) -> tuple[str, dict[str, Any]]:
    """Extract (kind, args) from an APScheduler trigger.

    Type-detection uses class name rather than `isinstance` so this stays
    decoupled from APScheduler internals (no extra imports needed at
    router collection time) and gracefully handles custom trigger
    subclasses — they fall through to the class-name fallback.
    """
    cls_name = type(trigger).__name__

    if cls_name == "CronTrigger":
        # `trigger.fields` is a list of field objects, each with `.name`
        # and a `__str__` that yields the field expression. Filter out
        # wildcards — `from_crontab(...)` produces literal `*` entries
        # for unspecified positions, which would otherwise dominate the
        # output.
        fields = getattr(trigger, "fields", []) or []
        args = {}
        for f in fields:
            value = str(f)
            if value != "*":
                args[f.name] = value
        return "cron", args

    if cls_name == "IntervalTrigger":
        # IntervalTrigger collapses weeks/days/hours/minutes/seconds into
        # a single `interval` timedelta — expose the canonical total in
        # seconds; consumers can derive minutes/hours as needed.
        interval = getattr(trigger, "interval", None)
        if interval is not None:
            return "interval", {"seconds": int(interval.total_seconds())}
        return "interval", {}

    if cls_name == "DateTrigger":
        run_date = getattr(trigger, "run_date", None)
        return "date", ({"run_date": run_date.isoformat()} if run_date else {})

    # Unknown / custom trigger — expose class name verbatim with no args.
    # Consumers see this as a structured signal that schema needs
    # extending rather than crash.
    return cls_name, {}


def _job_to_dto(job: Any) -> SchedulerJobDTO:
    """Convert an APScheduler `Job` into the boundary DTO.

    `next_run_time` is in `Job.__slots__` but APScheduler only assigns
    it once the scheduler is started (pre-start jobs sit in
    `_pending_jobs` with no `next_run_time` set). Accessing the slot
    before assignment raises `AttributeError`, so we use `getattr` with
    a `None` default to surface the canonical "not yet scheduled" state.
    """
    kind, args = _serialize_trigger(job.trigger)
    return SchedulerJobDTO(
        id=job.id,
        next_run_time=getattr(job, "next_run_time", None),
        trigger_kind=kind,
        trigger_args=args,
    )


def create_scheduler_router(deps) -> APIRouter:
    """Build the `/api/scheduler` router for a product.

    `deps` is the product's `ProductDependencies` instance — the router
    only calls `deps.get_current_user(authorization)` for the auth gate.
    """
    router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

    @router.get("/jobs", response_model=list[SchedulerJobDTO])
    async def list_jobs(
        authorization: Optional[str] = Header(None),
    ) -> list[SchedulerJobDTO]:
        """Return every job currently registered on the scheduler."""
        # Auth gate — raises 401 on missing / invalid token. Scheduler
        # state is platform-level; auth is required but org-scoping is
        # not. No filtering by user/org applied.
        await deps.get_current_user(authorization)
        return [_job_to_dto(j) for j in scheduler_module.scheduler.get_jobs()]

    @router.get("/jobs/{job_id}", response_model=SchedulerJobDTO)
    async def get_job(
        job_id: str,
        authorization: Optional[str] = Header(None),
    ) -> SchedulerJobDTO:
        """Return one scheduler job by id, or 404 if not registered."""
        await deps.get_current_user(authorization)
        job = scheduler_module.scheduler.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job nao encontrado")
        return _job_to_dto(job)

    return router
