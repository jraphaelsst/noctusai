"""Keep Geração from stranding work. The safety net.

Generation runs on a queue (``social_wiring.jobs``). If the process dies mid-job, or a job
dead-letters, nothing moves the DOMAIN row again and the UI polls a spinner forever. Two sweeps
(contract ``specs/geracao-contract.md`` section 3.2):

* :func:`sweep_stale` -- a headline batch / roteiro in ``criando`` or ``processando`` untouched for
  more than 15 minutes becomes ``falha`` ("Tempo esgotado -- tente novamente."); a viral whose
  classification has been ``processando`` for more than 15 minutes becomes ``falhou``.
  A roteiro in ``perguntas`` is waiting for the USER, so it is never stale. "Untouched" is
  ``updated_at``: the pipelines bump their row after every structure, so a live batch is not killed.
* :func:`sweep_dead_letters` -- for every dead-lettered queue row of a Geração job type, call the
  ``on_dead_letter`` reconciler its owner registered with
  :func:`~app.modules.media_creation.services.geracao_jobs.register_handler`, which moves the domain
  row to ``falha``. Idempotent: terminal rows are left alone.

Registered at IMPORT time via ``configure()`` (same idiom as ``cerebro_scheduler``).
``noctusai_lib.api.scheduler`` refuses to start unless ``NOCTUS_SCHEDULERS_ENABLED`` is set
(deployed containers only), so locally the job registers and never fires.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.domain.jobs import JobRepository

from app.dependencies import get_admin_client, get_scoped_admin_client
from app.modules.media_creation.services import geracao_jobs

logger = logging.getLogger(__name__)

JOB_ID = "geracao_stale_sweep"

#: A minute set no other job in this product uses (certidoes */5, cerebro :05/:15/..., card_hub :17,
#: imovel_hub :43). The thresholds decide staleness; the cron only decides how quickly a stranded
#: row is noticed.
CRON = "2,12,22,32,42,52 * * * *"

STALE_MINUTES = 15
MSG_TIMEOUT = "Tempo esgotado — tente novamente."
MSG_JOB_FAILED = "A geração falhou — tente novamente."

LOTES = "cs_headline_lotes"
ROTEIROS = "cs_roteiros"
VIRAIS = "cs_virais"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sweep_stale(db: Any, *, now: Optional[datetime] = None) -> dict[str, int]:
    """Move stranded rows to their failure state. Returns the count moved per kind."""
    now = now or _now()
    cutoff = (now - timedelta(minutes=STALE_MINUTES)).isoformat()
    stamp = now.isoformat()
    lotes = (
        db.table(LOTES)
        .update({"status": "falha", "erro": MSG_TIMEOUT, "finished_at": stamp})
        .in_("status", ["criando", "processando"])
        .lt("updated_at", cutoff)
        .execute().data
        or []
    )
    roteiros = (
        db.table(ROTEIROS)
        .update({"status": "falha", "erro": MSG_TIMEOUT, "finished_at": stamp})
        .in_("status", ["criando", "processando"])
        .lt("updated_at", cutoff)
        .execute().data
        or []
    )
    virais = (
        db.table(VIRAIS)
        .update({"classificacao_status": "falhou", "classificacao_erro": MSG_TIMEOUT})
        .eq("classificacao_status", "processando")
        .lt("updated_at", cutoff)
        .execute().data
        or []
    )
    return {"lotes": len(lotes), "roteiros": len(roteiros), "virais": len(virais)}


async def sweep_dead_letters(db: Any, repo: JobRepository, *, limit: int = 100) -> int:
    """Reconcile the domain rows of dead-lettered Geração jobs. Returns how many jobs had a
    reconciler called. A reconciler that raises is logged and skipped (the next run retries it)."""
    handled = 0
    for job_type in geracao_jobs.ALL_JOB_TYPES:
        reconcile = geracao_jobs.get_reconciler(job_type)
        if reconcile is None:
            continue
        for job in await repo.list_dead_letters(type=job_type, limit=limit):
            try:
                reconcile(db, job)
                handled += 1
            except Exception:  # noqa: BLE001 - one bad row must not stop the sweep
                logger.exception("geracao sweep: reconciler for %s failed (job %s)", job_type, job.id)
    return handled


def _client():
    if get_admin_client() is None:
        logger.warning("geracao sweep: no admin client — skipping run")
        return None
    return get_scoped_admin_client()


async def sweep_stranded(
    *,
    client: Optional[Callable[[], Any]] = None,
    repo: Optional[JobRepository] = None,
) -> None:
    """Never raises: a scheduler job that throws can silently stop being scheduled — which would
    remove the very safety net this is. ``client`` / ``repo`` are the DI seams so a test drives the
    sweep against a mock DB and a fake queue and asserts on the ROWS it did or did not touch."""
    resolve = client or _client
    try:
        db = resolve()
        if db is None:
            return
        moved = sweep_stale(db)
        if any(moved.values()):
            logger.info("geracao sweep: settled stale rows %s", moved)
        queue = repo or geracao_jobs.make_jobs_repository(db)
        reconciled = await sweep_dead_letters(db, queue)
        if reconciled:
            logger.info("geracao sweep: reconciled %d dead-lettered jobs", reconciled)
    except Exception as exc:  # noqa: BLE001 - scheduler job must not die
        logger.error("geracao sweep: run failed: %s", exc, exc_info=True)


def configure() -> None:
    """Register the sweep on the seed-side scheduler. Idempotent. Must run at import time, before
    ``start_scheduler()`` fires in ``app/lifespan.py``."""
    seed_scheduler.register(JOB_ID, sweep_stranded, cron=CRON)
    logger.info("geracao scheduler configured: stale + dead-letter sweep (cron %r)", CRON)


__all__ = [
    "CRON",
    "JOB_ID",
    "MSG_JOB_FAILED",
    "MSG_TIMEOUT",
    "STALE_MINUTES",
    "configure",
    "sweep_dead_letters",
    "sweep_stale",
    "sweep_stranded",
]
