"""
Background scheduler for recurring transaction execution.

Runs via APScheduler's AsyncIOScheduler inside the FastAPI lifespan.
Two triggers:
  - Daily at 06:00 Sao Paulo time (main run)
  - Every 4 hours for intraday catchup
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Silence APScheduler's verbose DEBUG logging
logging.getLogger("apscheduler").setLevel(logging.WARNING)

from app.dependencies import get_admin_client
from app.services.recorrentes_service import RecorrentesService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


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


def start_scheduler():
    """Register jobs and start the scheduler."""
    scheduler.add_job(
        executar_recorrentes_job,
        trigger=CronTrigger(hour=6, timezone="America/Sao_Paulo"),
        id="recorrentes_daily",
        replace_existing=True,
    )
    scheduler.add_job(
        executar_recorrentes_job,
        trigger=IntervalTrigger(hours=4),
        id="recorrentes_catchup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started with daily (06:00) and 4h interval triggers")


def stop_scheduler():
    """Shut down the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
