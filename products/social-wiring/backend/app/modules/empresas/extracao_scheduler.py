"""Recover Cartão CNPJ extractions that were started and never finished —
mirrors `card_hub.extracao_scheduler` / `imovel_hub.extracao_scheduler`'s
identical shape (the never-raise wrapper and the no-storage skip live once,
in `app.services.extraction_sweep`).
"""
from __future__ import annotations

import logging

from app.services.extraction_sweep import configure_sweep, make_sweep_job

logger = logging.getLogger(__name__)

JOB_ID = "empresas_extracao_sweep"

#: Every hour at :23 — off the hour and offset from the other extraction
#: sweeps (card_hub :17, imovel_hub/matriculas at their own offsets), so
#: they do not all pile onto the same minute.
CRON = "23 * * * *"


async def _sweep(admin, storage) -> dict:
    from app.modules.empresas import sweep_service
    from app.modules.empresas.deps import (
        get_cartao_extractor_factory,
        get_empresa_notification_service,
    )

    try:
        notificador = get_empresa_notification_service()
    except Exception:  # noqa: BLE001 - a notifier outage must not stop recovery
        logger.exception("empresas sweep: notification service unavailable")
        notificador = None
    return await sweep_service.varrer_extracoes_pendentes(
        admin, storage,
        extractor_factory=get_cartao_extractor_factory(),
        notification_service=notificador,
    )


extracao_sweep_job = make_sweep_job(label="empresas", sweep=_sweep)


def configure() -> None:
    """Register the sweep on the seed-side scheduler. Idempotent. Must run
    at IMPORT time, before `start_scheduler()` fires in `app/lifespan.py`."""
    configure_sweep(
        job_id=JOB_ID, cron=CRON, label="empresas", sweep=_sweep, job=extracao_sweep_job,
    )


__all__ = ["CRON", "JOB_ID", "configure", "extracao_sweep_job"]
