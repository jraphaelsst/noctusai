"""Build a scheduled "recover the stranded extractions" job. One definition.

🔴 WHY THESE SWEEPS EXIST AT ALL
---------------------------------
Every extraction runs in a FastAPI `BackgroundTask`, detached from the
request that uploaded the document. `extracao_status` moves to `processando`
before the work and to a terminal value after it. If the process dies in
between — a deploy, an OOM kill, a container restart — **nothing ever moves
it again**. The document sits there, the field never fills, and nothing
surfaces: no error, no alert, no retry. The same is true of `pendente` when
the process went away before the task was ever scheduled.

That is a silent error with a schedule attached: every deploy is an
opportunity to strand whatever was mid-read.

🔴 WHY THE WIRING IS SHARED AND NOT COPIED
-------------------------------------------
`card_hub` (identity documents) and `imovel_hub` (matrículas) both need one,
and the parts they share are exactly the parts whose absence is invisible:

- the **never-raise** wrapper — a scheduler job that throws is, in some
  runtimes, a job that silently stops being scheduled, which removes the very
  safety net this is;
- the **no-storage skip** — in a mock/sqlite environment the admin client has
  no `.storage`, and sweeping against it would produce a confusing failure
  every hour instead of one honest log line.

A copy that drops either one still passes every test and still *looks* like a
safety net. That is the criterion for centralising, and it is met here.

What is NOT shared is the schedule or the job id: each caller declares its
own, so two sweeps do not land on the same minute.

WHY NO LEASE
------------
`sync_leases` (migration 070) exists because the nightly Vista sync must not
run twice concurrently. These sweeps have no such requirement: each document
is re-read through a function that stamps `processando` and increments
`extracao_tentativas` before doing any work, so a duplicated sweep costs at
worst a repeated read of an already-claimed row. A lease would add a failure
mode (a wedged lease stops recovery entirely) to protect against a cost we
do not pay.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)

#: `(admin_client, storage_backend) -> awaitable[dict]`. The dict is expected
#: to carry an `encontrados` count, which is what decides whether the run is
#: worth a log line.
SweepFn = Callable[[Any, Any], Awaitable[dict]]


def make_sweep_job(
    *,
    label: str,
    sweep: SweepFn,
) -> Callable[[], Awaitable[None]]:
    """Wrap a sweep in the guards every scheduled sweep needs.

    `sweep` is called with `(admin_client, storage_backend)` and may raise —
    that is the point of the wrapper.
    """

    async def job() -> None:
        try:
            from noctusai_lib.integrations.storage import make_storage_backend

            admin = get_admin_client()
            if admin is None:
                logger.warning("%s sweep: no admin client — skipping run", label)
                return
            if not hasattr(admin, "storage"):
                # Mock/sqlite fallback in a non-prod environment. Say so
                # rather than sweeping against a backend that cannot read
                # blobs and failing opaquely every hour.
                logger.info("%s sweep: client has no storage — skipping run", label)
                return

            result = await sweep(
                admin, make_storage_backend(kind="supabase", client=admin)
            )
            if result and result.get("encontrados"):
                logger.info("%s sweep: %s", label, result)
        except Exception as exc:  # noqa: BLE001 - scheduler job must not die
            logger.error("%s sweep: run failed: %s", label, exc, exc_info=True)

    job.__name__ = f"{label}_sweep_job"
    return job


def configure_sweep(
    *,
    job_id: str,
    cron: str,
    label: str,
    sweep: SweepFn,
    job: Optional[Callable[[], Awaitable[None]]] = None,
) -> Callable[[], Awaitable[None]]:
    """Register a sweep on the seed-side scheduler. Idempotent.

    Must be called at IMPORT time, before `start_scheduler()` fires in
    `app/lifespan.py`, or the job is never registered and the safety net
    silently does not exist.
    """
    job = job or make_sweep_job(label=label, sweep=sweep)
    seed_scheduler.register(job_id, job, cron=cron)
    logger.info("%s extraction sweep configured (cron %r)", label, cron)
    return job


__all__ = ["SweepFn", "configure_sweep", "make_sweep_job"]
