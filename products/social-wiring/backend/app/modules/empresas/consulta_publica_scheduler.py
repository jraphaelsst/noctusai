"""Hourly catch-up — resolve `situacao_cadastral` for every `empresas` row
the automatic (c2) fill at Crednet-creation time missed. See `consulta_
publica_service.py`'s own docstring for why this is NOT built on `empresas
.extracao_scheduler`/`app.services.extraction_sweep`: this pass needs no
blob storage at all (there is no document, only a public API call), so
`extraction_sweep.make_sweep_job`'s own "no storage -> skip" guard would
incorrectly skip this job in exactly the environments (mock/sqlite tests,
or a genuine storage outage) where it should still run fine — the job body
here is its own small never-raise wrapper instead.
"""
from __future__ import annotations

import logging

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)

JOB_ID = "empresas_consulta_publica_cnpj_sweep"

#: Every hour at :41 — off the hour and offset from every OTHER extraction
#: sweep already registered (card_hub :17, imovel_hub/matriculas at their
#: own offsets, empresas' own Cartão CNPJ sweep at :23), so they never pile
#: onto the same minute.
CRON = "41 * * * *"


async def _job() -> None:
    try:
        admin = get_admin_client()
        if admin is None:
            logger.warning("empresas consulta_publica sweep: no admin client — skipping run")
            return

        from app.modules.empresas import consulta_publica_service
        from app.modules.empresas.deps import get_cnpj_registry_lookup

        resultado = await consulta_publica_service.resolver_pendentes(
            admin, get_cnpj_registry_lookup(),
        )
        if resultado.get("encontrados"):
            logger.info("empresas consulta_publica sweep: %s", resultado)
    except Exception as exc:  # noqa: BLE001 - scheduler job must not die
        logger.error("empresas consulta_publica sweep: run failed: %s", exc, exc_info=True)


def configure() -> None:
    """Register the sweep on the seed-side scheduler. Idempotent. Must run
    at IMPORT time, before `start_scheduler()` fires in `app/lifespan.py`
    — same contract every other `configure()` in this product already
    documents (`empresas.extracao_scheduler.configure`, etc.)."""
    seed_scheduler.register(JOB_ID, _job, cron=CRON)
    logger.info("empresas consulta_publica_cnpj sweep configured (cron %r)", CRON)


__all__ = ["CRON", "JOB_ID", "configure"]
