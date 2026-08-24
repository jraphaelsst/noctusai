"""Recover identity extractions that were started and never finished.

🔴 WHY THIS IS NOT OPTIONAL POLISH
-----------------------------------
Extraction runs in a FastAPI ``BackgroundTask``, detached from the request
that uploaded the document. ``extracao_status`` moves to ``processando``
before the work and to a terminal value after it. If the process dies in
between — a deploy, an OOM kill, a container restart — **nothing ever moves
it again**. The document sits in ``processando`` forever, its checklist item
never ticks, and nothing surfaces: no error, no alert, no retry. The same is
true of ``pendente`` when the handler's process went away before the task was
ever scheduled.

That is a silent error with a schedule attached — every deploy is an
opportunity to strand whatever was mid-read. This job is the recovery.

WHY HOURLY, AND WHY NOT MORE OFTEN
----------------------------------
``STALE_APOS`` (20 minutes) is what actually decides whether a document is
abandoned; the cron only decides how quickly a genuinely-stranded one is
noticed. Hourly means a stranded document waits at most an hour, which is
well inside "the operator has not come back to this card yet", while keeping
the sweep's own query count trivial.

WHY IT DOES NOT NEED A LEASE
----------------------------
``sync_leases`` (migration 070) exists because the nightly Vista sync must not
run twice concurrently. This sweep has no such requirement: each document is
re-read through ``extrair_identidade``, which stamps ``processando`` and
increments ``extracao_tentativas`` before doing any work, so a duplicated
sweep costs at worst a repeated read of an already-claimed row rather than
corrupting anything — and ``MAX_TENTATIVAS`` bounds even that. Taking a lease
here would add a failure mode (a wedged lease stops recovery entirely) to
protect against a cost we do not pay.
"""
from __future__ import annotations

import logging

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)

JOB_ID = "card_hub_extracao_sweep"

#: Every hour at :17. Off the hour on purpose — the top of the hour is where
#: every other scheduled job in the fleet already piles up.
CRON = "17 * * * *"


async def extracao_sweep_job() -> None:
    """Sweep once. Never raises — a scheduler job that throws is a job that
    silently stops being scheduled in some runtimes, which would remove the
    very safety net this is."""
    try:
        from noctusai_lib.integrations.storage import make_storage_backend

        from app.modules.card_hub import identidade_extracao_service as identidade_svc
        from app.modules.card_hub.deps import get_identity_extractor_factory

        admin = get_admin_client()
        if admin is None:
            logger.warning("extracao sweep: no admin client — skipping run")
            return
        if not hasattr(admin, "storage"):
            # Mock/sqlite fallback in a non-prod environment. Say so rather
            # than sweeping against a backend that cannot read blobs.
            logger.info("extracao sweep: client has no storage — skipping run")
            return

        result = await identidade_svc.varrer_extracoes_pendentes(
            admin,
            make_storage_backend(kind="supabase", client=admin),
            extractor_factory=get_identity_extractor_factory(),
        )
        if result["encontrados"]:
            logger.info("extracao sweep: %s", result)
    except Exception as exc:  # noqa: BLE001 - scheduler job must not die
        logger.error("extracao sweep: run failed: %s", exc, exc_info=True)


def configure() -> None:
    """Register the sweep on the seed-side scheduler.

    Must be called at IMPORT time, before ``start_scheduler()`` fires in
    ``app/lifespan.py``, or the job is never registered and the safety net
    silently does not exist. Idempotent.
    """
    seed_scheduler.register(JOB_ID, extracao_sweep_job, cron=CRON)
    logger.info("card_hub extracao sweep configured (cron %r)", CRON)


__all__ = ["CRON", "JOB_ID", "configure", "extracao_sweep_job"]
