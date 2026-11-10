"""Daily Vista roster sync of the in-house brokers, for every org with a Vista credential (seed scheduler + per-org `sync_lease`).

Same shape as `ad_lead_intake_retry_job` / `imoveis_sync_scheduler`: interval job, per-org DB lease `corretores_vista_sync:<org>` (a second
process or a manual run skips), failures isolated per org and logged with context. Orgs = those with a Vista credential record
(`imoveis_sync_scheduler._orgs_with_credential`); an org whose adapter cannot be built is skipped, logged.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler

from app.modules.leads.services import corretores_vista_sync as sync

logger = logging.getLogger(__name__)

JOB_NAME = "corretores_vista_sync"
INTERVALO_S = 24 * 3600
LEASE_TTL_S = 1800
_MISFIRE_GRACE = 6 * 3600


async def corretores_vista_job(
    *, admin_factory: Any = None, discover_fn: Any = None, adapter_factory: Any = None, lease_fn: Any = None, sync_fn: Any = None,
) -> dict[str, Any]:
    from app.dependencies import get_admin_client
    from app.services import imoveis_sync_scheduler, sync_lease, vista_credenciais

    admin = (admin_factory or get_admin_client)()
    if admin is None:
        logger.error("%s: no admin client -- skipping", JOB_NAME)
        return {}
    try:
        org_ids = await asyncio.to_thread(discover_fn or imoveis_sync_scheduler._orgs_with_credential, admin)
    except Exception:
        logger.error("%s: org discovery failed", JOB_NAME, exc_info=True)
        return {}
    relatorio: dict[str, Any] = {}
    for org_id in org_ids:
        adapter = (adapter_factory or vista_credenciais.adapter_ou_none)(org_id)
        if adapter is None:
            logger.warning("%s: org=%s has no usable Vista credential -- skipped", JOB_NAME, org_id)
            continue
        cm = (lease_fn or (lambda nome: sync_lease.lease(admin, nome, ttl_seconds=LEASE_TTL_S)))(f"{JOB_NAME}:{org_id}")
        try:
            with cm as got:
                if not got:
                    relatorio[org_id] = {"pulado": "lease_ocupada"}
                    continue
                relatorio[org_id] = await (sync_fn or sync.sincronizar)(admin, adapter, UUID(str(org_id)))
        except Exception:
            logger.error("%s: org=%s failed", JOB_NAME, org_id, exc_info=True)
            relatorio[org_id] = {"erro": True}
    return relatorio


def configure() -> None:
    # poll-budget: every 24 h; ~1-3 corretores/listar pages/tick/org (50 per page); worst 3/day per org; idle=fixed
    seed_scheduler.register(JOB_NAME, corretores_vista_job, seconds=INTERVALO_S, misfire_grace_time=_MISFIRE_GRACE)
    logger.info("%s configured: every %ds", JOB_NAME, INTERVALO_S)


__all__ = ["JOB_NAME", "configure", "corretores_vista_job"]
