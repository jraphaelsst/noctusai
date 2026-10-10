"""Keep Segundo Cérebro from stranding work. The safety net.

Three states outlive the request that created them: a brain synthesis
(``processing``), an answer review (``pending``) and a file import
(``processing``) all run in ``BackgroundTasks``. If the process dies (deploy,
OOM kill, restart) nothing ever moves that row again and the UI polls a spinner
forever. :func:`sweep_stale` moves them to ``error`` after the contract's
thresholds (10 / 10 / 15 minutes).

Registered at IMPORT time via ``configure()`` (same idiom as
``app.modules.certidoes.scheduler``). ``noctusai_lib.api.scheduler`` refuses to
start unless ``NOCTUS_SCHEDULERS_ENABLED`` is set (deployed containers only), so
locally the job registers and never fires; that gap is closed from the other
side by ``CerebroService``'s throttled read-time refresh.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client, get_scoped_admin_client
from app.modules.media_creation.services.cerebro_service import sweep_stale

logger = logging.getLogger(__name__)

JOB_ID = "cerebro_stale_sweep"

#: A minute set no other job in this product uses (certidoes */5, card_hub :17,
#: imovel_hub :43); the thresholds decide staleness, the cron only decides how
#: quickly a stranded row is noticed.
CRON = "5,15,25,35,45,55 * * * *"


def _client():
    if get_admin_client() is None:
        logger.warning("cerebro sweep: no admin client — skipping run")
        return None
    return get_scoped_admin_client()


async def sweep_stranded(*, client: Optional[Callable[[], Any]] = None) -> None:
    """Never raises: a scheduler job that throws can silently stop being
    scheduled — which would remove the very safety net this is. ``client`` is the
    DI seam (default :func:`_client`) so a test drives the sweep against a mock
    DB and asserts on the ROWS it did or did not touch."""
    resolve = client or _client
    try:
        db = resolve()
        if db is None:
            return
        moved = sweep_stale(db)
        if any(moved.values()):
            logger.info("cerebro sweep: settled stale rows %s", moved)
    except Exception as exc:  # noqa: BLE001 - scheduler job must not die
        logger.error("cerebro sweep: run failed: %s", exc, exc_info=True)


def configure() -> None:
    """Register the sweep on the seed-side scheduler. Idempotent. Must run at
    import time, before ``start_scheduler()`` fires in ``app/lifespan.py``."""
    seed_scheduler.register(JOB_ID, sweep_stranded, cron=CRON)
    logger.info("cerebro scheduler configured: stale sweep (cron %r)", CRON)


__all__ = ["CRON", "JOB_ID", "configure", "sweep_stranded"]
