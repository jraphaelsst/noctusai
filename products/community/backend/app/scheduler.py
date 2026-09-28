"""Background jobs for Community — on the seed scheduler primitive
(`noctusai_lib.api.scheduler`), same shape as Core's `app/scheduler.py`.

`configure()` registers at import (called from `app/main.py`);
`start_scheduler` / `stop_scheduler` are the seed's own, so NOTHING here
fires unless the process carries `NOCTUS_SCHEDULERS_ENABLED` (set only in
the deployed compose) — a laptop running against the production `.env`
never sweeps production subscriptions.

Jobs (America/Sao_Paulo):

* `community_rotina_cobranca` — hourly at :20. The Ninho Vazio billing
  sweep (`app/services/cobranca_service.py`): pending gateway cancels,
  grace expiry → free plan, end of a cancelled subscription's paid period
  → free plan. Honors `configuracoes_cobranca.automacoes_ativas`.

Each job body takes an optional service so tests run it on Fakes; errors
are logged (a job must not take the scheduler down), never swallowed.
"""
from __future__ import annotations

import logging
from typing import Optional

from noctusai_lib.api.scheduler import register, start_scheduler, stop_scheduler

from app.dependencies import get_admin_client, resolve_public_org_id
from app.services.cobranca_service import CobrancaService

logger = logging.getLogger(__name__)

ROTINA_COBRANCA_JOB = "community_rotina_cobranca"


async def rotina_cobranca_job(service: Optional[CobrancaService] = None) -> list[dict]:
    """Run the billing sweep for this single-tenant product's org."""
    try:
        if service is None:
            # Single-tenant (MASTER-PROMPT.md): the org licensed for this
            # product — the same resolution the public routes use.
            service = CobrancaService(get_admin_client(), org_id=resolve_public_org_id())
        relatorios = await service.executar_rotina()
    except Exception as exc:  # noqa: BLE001 — logged; the scheduler must keep running
        logger.error("cobranca: rotina agendada falhou: %s", exc, exc_info=True)
        return [{"erro": str(exc)}]
    return [r.como_dict() for r in relatorios]


def configure() -> None:
    """Register every Community job (idempotent — re-registering replaces)."""
    register(ROTINA_COBRANCA_JOB, rotina_cobranca_job, cron="20 * * * *", misfire_grace_time=1800)


__all__ = [
    "ROTINA_COBRANCA_JOB",
    "configure",
    "rotina_cobranca_job",
    "start_scheduler",
    "stop_scheduler",
]
