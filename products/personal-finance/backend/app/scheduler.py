"""Personal Finance backend scheduler — migrated to `noctusai_lib.api.scheduler`.

Two triggers (intentionally — daily run + intraday catch-up):
  - Daily at 06:00 São Paulo time (main run)
  - Every 4 hours for intraday catch-up

The job body is identical for both triggers (`executar_recorrentes_job`);
only the cadence differs.
"""
from __future__ import annotations

import logging

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client
from app.services.recorrentes_service import RecorrentesService

logger = logging.getLogger(__name__)


async def executar_recorrentes_job():
    """Iterate all orgs with active automatic recurrences and execute pending."""
    logger.info("Scheduler: starting recurring transaction execution")

    try:
        db = get_admin_client()

        # Get distinct org_ids that have active automatic recurrences
        result = db.table("recorrentes").select("org_id").eq(
            "ativo", True
        ).eq("is_automatico", True).execute()

        if not result.data:
            logger.info("Scheduler: no active automatic recurrences found")
            return

        # Deduplicate org_ids
        org_ids = list({row["org_id"] for row in result.data})
        total_executadas = 0
        total_erros = 0

        for org_id in org_ids:
            try:
                service = RecorrentesService(db, org_id)
                summary = await service.executar_pendentes()
                total_executadas += summary.get("executadas", 0)
                total_erros += summary.get("erros", 0)
            except Exception as exc:
                logger.error(f"Scheduler: error processing org {org_id}: {exc}")
                total_erros += 1

        logger.info(
            "Scheduler: completed recurring execution — "
            "orgs=%d executed=%d errors=%d",
            len(org_ids),
            total_executadas,
            total_erros,
        )
    except Exception as exc:
        logger.error(f"Scheduler: unexpected error in recurring job: {exc}")


def configure() -> None:
    """Register PF's recurring jobs on the seed-side scheduler."""
    seed_scheduler.register(
        "recorrentes_daily",
        executar_recorrentes_job,
        cron="0 6 * * *",
    )
    seed_scheduler.register(
        "recorrentes_catchup",
        executar_recorrentes_job,
        hours=4,
    )
    logger.info(
        "PF scheduler configured: recorrentes daily (06:00 SP cron) + "
        "4h interval catch-up"
    )


# Re-export so `main.py`'s lifespan wiring is unchanged.
start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler
