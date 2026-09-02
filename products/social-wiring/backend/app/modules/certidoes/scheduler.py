"""Keep the certidões pipeline from stranding work. The safety net.

🔴 WHAT STRANDS, AND WHY NOTHING ELSE NOTICES
----------------------------------------------
Two states in this module outlive the request that created them:

- `processando` — a `BackgroundTask` is mid-flight against InfoSimples. If the
  process dies (deploy, OOM kill, container restart), **nothing ever moves that
  row again**. The frontend polls a spinner forever, and no error is raised
  anywhere.
- `na_fila` — a TJSP item waiting out the 45-minute cooldown, held by an
  in-memory `asyncio.Task`. A restart takes the task with it and leaves the row
  queued behind a timer that no longer exists.

Both are silent errors with a schedule attached: every deploy is an opportunity
to strand whatever was in flight.

🔴 WHY A RECURRING SWEEP AND NOT THE ERP'S LIFESPAN HOOK
---------------------------------------------------------
ERP wired `recover_stuck_processando` + `schedule_all_pending_tjsp` into its
`lifespan_startup`. This module registers a job on the seed scheduler at import
time instead — the same `configure()`-before-`start_scheduler()` idiom
`imovel_hub.extracao_scheduler` and `card_hub.extracao_scheduler` use, and the
one `app/main.py`'s `_register_media_wiring` documents.

The sweep calls `recover_stale_processando`, NOT `recover_stuck_processando`.
That is the whole reason it is safe to run repeatedly: the stale variant only
touches rows whose `api_requested_at` is more than 15 minutes old, and the
slowest legitimate run (240s timeout × 3 retries) is ~12 minutes — so a live
request is never reset out from under itself. `recover_stuck_processando` is
unconditional and would do exactly that; it is correct only at process start,
which is what `run_startup_recovery` below is for.

This is also strictly BETTER than boot-only on one axis: ERP re-scheduled lost
TJSP tasks only at startup, so a task cancelled mid-run (or lost to an
exception the chain did not re-arm) stayed lost until the next deploy. Here it
is picked up on the next tick.

🔴 WHAT THIS DOES NOT COVER, SAID OUT LOUD
-------------------------------------------
`noctusai_lib.api.scheduler.start_scheduler()` refuses to start unless
`NOCTUS_SCHEDULERS_ENABLED` is set, which only deployed containers carry. So on
a laptop this job registers and never fires. That gap is closed from the other
side: `routers/certidoes.py`'s consulta listing runs the same stale-recovery
and per-org TJSP rescheduling on a 60-second throttle, on the caller's own org
— which is exactly when a human is looking at the screen the stranded row is
on. Neither leg alone is sufficient; together the queue resumes whether or not
the scheduler is authorised in this environment.
"""
from __future__ import annotations

import logging

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client, get_scoped_admin_client
from app.modules.certidoes import service
from app.modules.certidoes.deps import storage_for

logger = logging.getLogger(__name__)

JOB_ID = "certidoes_stranded_sweep"

#: Every 5 minutes. Not time-sensitive — `STALE_PROCESSANDO_SECONDS` (15 min)
#: is what decides whether a row is abandoned; the cron only decides how
#: quickly a genuinely stranded one is noticed. A minute that no other sweep in
#: this product uses (`card_hub` :17, `imovel_hub` :43) so the bursts do not
#: stack, and short enough that a TJSP queue lost to a restart resumes well
#: inside its own 45-minute cooldown.
CRON = "*/5 * * * *"


def _clients():
    """`(scoped_client, storage)` or `(None, None)` when unavailable.

    The scoped client is what every query in `service.py` expects (it is
    `social_wiring`-scoped); the storage backend must bind to the RAW admin
    client, because `.storage` lives on the top-level Supabase client and never
    on a `.schema(...)`-derived proxy.
    """
    admin = get_admin_client()
    if admin is None:
        logger.warning("certidoes sweep: no admin client — skipping run")
        return None, None
    return get_scoped_admin_client(), storage_for(admin)


async def sweep_stranded() -> None:
    """Recover stale `processando` rows and re-arm the TJSP queue.

    Never raises: a scheduler job that throws is, in some runtimes, a job that
    silently stops being scheduled — which would remove the very safety net
    this is.
    """
    try:
        db, storage = _clients()
        if db is None:
            return
        recovered = service.recover_stale_processando(db)
        if recovered:
            logger.info("certidoes sweep: recovered %d stale resultado(s)", recovered)
        service.schedule_all_pending_tjsp(db, storage)
    except Exception as exc:  # noqa: BLE001 - scheduler job must not die
        logger.error("certidoes sweep: run failed: %s", exc, exc_info=True)


def run_startup_recovery() -> None:
    """The ERP `lifespan_startup` pair, for a caller that HAS a startup hook.

    🔴 Correct ONLY at process start. `recover_stuck_processando` is
    unconditional — at any other moment it resets rows a live task in this very
    process is working on. Not wired into `app/lifespan.py` by this slice
    (`main.py`/`lifespan.py` belong to the integration step); the recurring
    `sweep_stranded` above covers the same ground within one tick, so this is an
    optional latency improvement, not a missing piece.
    """
    try:
        db, storage = _clients()
        if db is None:
            return
        service.recover_stuck_processando(db)
        service.schedule_all_pending_tjsp(db, storage)
    except Exception as exc:  # noqa: BLE001 - startup must not be fatal
        # A lifespan hook is a SIDE EFFECT, never a precondition for serving.
        # → KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md
        logger.error(
            "certidoes: startup recovery failed: %s", exc, exc_info=True
        )


def configure() -> None:
    """Register the sweep on the seed-side scheduler. Idempotent.

    Must be called at IMPORT time, before `start_scheduler()` fires in
    `app/lifespan.py`, or the job is never registered and the safety net
    silently does not exist.
    """
    seed_scheduler.register(JOB_ID, sweep_stranded, cron=CRON)
    logger.info("certidoes stranded sweep configured (cron %r)", CRON)


__all__ = ["CRON", "JOB_ID", "configure", "run_startup_recovery", "sweep_stranded"]
