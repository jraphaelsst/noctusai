"""Daily "Visita de {cliente} aconteceu?" prompt (CONTRACT sw-lead-to-contract §3.2).

One digest per org, every morning, listing the roteiros whose visit date passed
with no answer. Re-sent daily until answered: an unanswered roteiro is exactly
the data hole the funnel metric cannot see, so the nag IS the feature.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler

from app.modules.card_hub import roteiros_feedback_service as feedback_svc
from app.services import table_reads

logger = logging.getLogger(__name__)

JOB_ID = "card_hub_roteiros_feedback_prompt"
#: 11:00 UTC = 08:00 São Paulo.
CRON = "0 11 * * *"


def _orgs_com_roteiros(client: Any) -> list[UUID]:
    from noctusai_lib.integrations.persistence import iter_paged_rows

    def fetch_page(start: int, end: int):
        return (
            table_reads.table(client, "roteiros")
            .select("id, org_id")
            .eq("feedback_status", "pendente")
            .is_("deleted_at", "null")
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    vistos = {
        str(r["org_id"])
        for r in iter_paged_rows(fetch_page, label="roteiros pendentes org scan")
        if r.get("org_id")
    }
    return [UUID(o) for o in sorted(vistos)]


async def avisar_todas_orgs(client: Any, notifier: Any) -> dict:
    """Returns `{orgs, roteiros, falhas}`; one org's failure never stops the rest."""
    resumo = {"orgs": 0, "roteiros": 0, "falhas": 0}
    for org_id in _orgs_com_roteiros(client):
        try:
            pend = feedback_svc.pendentes(client, org_id)
            if not pend:
                continue
            await notifier.notify_visita_feedback(org_id=org_id, pendentes=pend)
            resumo["orgs"] += 1
            resumo["roteiros"] += len(pend)
        except Exception:  # noqa: BLE001 - one org must not stop the others
            resumo["falhas"] += 1
            logger.error("roteiros feedback prompt failed for org %s", org_id, exc_info=True)
    return resumo


async def job(*, client: Optional[Any] = None, notifier: Optional[Any] = None) -> None:
    """Scheduler entrypoint; never raises (a throwing job can be de-registered)."""
    try:
        from app.modules.card_hub.deps import (
            get_card_hub_client,
            get_conflict_notification_service,
        )

        resumo = await avisar_todas_orgs(
            client or get_card_hub_client(), notifier or get_conflict_notification_service()
        )
        logger.info("roteiros feedback prompt: %s", resumo)
    except Exception:  # noqa: BLE001
        logger.error("roteiros feedback prompt job failed", exc_info=True)


def configure() -> None:
    """Register on the seed scheduler at import time (before `start_scheduler()`)."""
    seed_scheduler.register(JOB_ID, job, cron=CRON)
    logger.info("card_hub roteiros feedback prompt configured: %s", CRON)


__all__ = ["CRON", "JOB_ID", "avisar_todas_orgs", "configure", "job"]
