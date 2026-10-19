"""Maya's two seed-scheduler jobs (maya-blocks CONTRACT §2.3 / §3.1 / §3.4).

- `supervisao_scorecards_diario` -- 07:00 America/Sao_Paulo (the seed scheduler's timezone): for every org with
  `supervisao_ativa`, upsert the last 7 days of scorecards for each `ativo` block, then send yesterday's report
  to the owner (in-app + email, once per day).
- `supervisao_handoffs_sweep` -- every 15 min: the blocks slice's status machine `handoffs.varrer`
  (`emitido` -> `assumido` / `expirado`) for every supervised org.

Registered at IMPORT time via `configure()` (before `start_scheduler()` in app/lifespan.py); the seed scheduler
only fires when `NOCTUS_SCHEDULERS_ENABLED` is on (deployed containers). Never raises: a job that throws can
silently stop being scheduled, and one org's failure must not stop the others.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler

from app.modules.atendimento_blocos import handoffs
from app.modules.supervisao import metricas as m
from app.modules.supervisao import relatorio
from app.modules.supervisao import service as svc

logger = logging.getLogger(__name__)

JOB_DIARIO = "supervisao_scorecards_diario"
CRON_DIARIO = "0 7 * * *"
JOB_SWEEP = "supervisao_handoffs_sweep"
#: :04 / :19 / :34 / :49 -- off the minutes the product's other sweeps use.
CRON_SWEEP = "4,19,34,49 * * * *"


def _client() -> Any:
    from app.dependencies import get_scoped_admin_client

    return get_scoped_admin_client("social_wiring")


def _core() -> Any:
    from app.dependencies import get_core_client

    return get_core_client()


async def executar_diario(*, client: Any, core: Any, agora: datetime,
                          sender_factory: Optional[Callable[[], Any]] = None) -> dict[str, Any]:
    """One nightly pass over every supervised org. Returns per-org outcomes (for logs / tests)."""
    out: dict[str, Any] = {}
    ontem = m.hoje_sp(agora) - timedelta(days=1)
    for org_id in svc.orgs_supervisionadas(client):
        try:
            handoffs.varrer(client, org_id, agora=agora)  # fresh statuses before scoring them
            escritos = svc.computar_scorecards(client, org_id, agora=agora)
            kw = {"sender_factory": sender_factory} if sender_factory is not None else {}
            rel = await relatorio.enviar_relatorio(client, core, org_id, ontem, **kw)
            out[org_id] = {"scorecards": len(escritos), "relatorio": rel}
        except Exception:
            logger.exception("supervisao: nightly pass failed for org=%s", org_id)
            out[org_id] = {"erro": True}
    return out


def executar_sweep(*, client: Any, agora: datetime) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for org_id in svc.orgs_supervisionadas(client):
        try:
            out[org_id] = handoffs.varrer(client, org_id, agora=agora)
        except Exception:
            logger.exception("supervisao: handoff sweep failed for org=%s", org_id)
            out[org_id] = {"erro": True}
    return out


async def run_diario(*, client: Optional[Callable[[], Any]] = None, core: Optional[Callable[[], Any]] = None) -> None:
    """Scheduled entry. `client` / `core` are DI seams."""
    try:
        resultado = await executar_diario(client=(client or _client)(), core=(core or _core)(), agora=svc.agora_utc())
        logger.info("supervisao: nightly scorecards %s", resultado)
    except Exception:  # noqa: BLE001 - a scheduler job must not die
        logger.exception("supervisao: nightly run failed")


async def run_sweep(*, client: Optional[Callable[[], Any]] = None) -> None:
    try:
        resultado = executar_sweep(client=(client or _client)(), agora=svc.agora_utc())
        if any(any(v.values()) for v in resultado.values() if isinstance(v, dict)):
            logger.info("supervisao: handoff sweep %s", resultado)
    except Exception:  # noqa: BLE001 - a scheduler job must not die
        logger.exception("supervisao: handoff sweep run failed")


def configure(*, scheduler: Any = None) -> None:
    """Register both jobs on the seed scheduler. Idempotent."""
    sched = scheduler or seed_scheduler
    # an hour of grace: a deploy restarting the container at 07:00 must not skip the owner's day
    sched.register(JOB_DIARIO, run_diario, cron=CRON_DIARIO, misfire_grace_time=3600)
    sched.register(JOB_SWEEP, run_sweep, cron=CRON_SWEEP)
    logger.info("supervisao scheduler configured: scorecards %r, handoff sweep %r", CRON_DIARIO, CRON_SWEEP)


__all__ = ["CRON_DIARIO", "CRON_SWEEP", "JOB_DIARIO", "JOB_SWEEP", "configure", "executar_diario", "executar_sweep"]
