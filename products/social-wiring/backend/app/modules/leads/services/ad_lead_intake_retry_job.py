"""Retry job of the ad-lead intake: drains `lead_imovel_intakes` rows in `pendente_retry` (Vista was down / not configured).

Interval job on the seed scheduler (every `INTERVALO_S`), same shape as `imoveis_sync_scheduler`: a per-org DB lease
(`sync_lease`, name `ad_lead_intake_retry:<org>`) keeps two processes from draining the same org; failures are isolated per
org and per lead and logged with context, nothing re-raises into APScheduler.

BACKOFF: a row is eligible once `updated_at + min(BASE_S * 2**(tentativas-1), CAP_S)` has passed (5 min, 10, 20 ... capped at 6 h),
so a Vista outage is probed at a decaying rate instead of hammered. `intake` flips a row to `falhou` after
`MAX_TENTATIVAS_AUTO` attempts -- the job never touches `falhou` (a human re-drives it: backfill `modo=pendentes` or the retry endpoint).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler

from app.modules.leads.services import ad_lead_intake_service as intake

logger = logging.getLogger(__name__)

JOB_NAME = "ad_lead_intake_retry"
INTERVALO_S = 600
BASE_S = 300
CAP_S = 6 * 3600
LOTE_POR_ORG = 25
LEASE_TTL_S = 1800
_MISFIRE_GRACE = 3600


def backoff(tentativas: int) -> timedelta:
    return timedelta(seconds=min(BASE_S * 2 ** max(0, int(tentativas) - 1), CAP_S))


def _parse(ts: Any) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def elegiveis(client: Any, now: datetime, *, limite: int = 500) -> dict[str, list[dict]]:
    """`{org_id: [intake rows due for a retry]}` (oldest first). A row with an unreadable `updated_at` is due (retry beats a stuck row)."""
    rows = (
        client.table(intake.T_INTAKES).select("id,org_id,lead_id,tentativas,updated_at").eq("status", intake.ST_RETRY)
        .order("updated_at").limit(limite).execute().data or []
    )
    por_org: dict[str, list[dict]] = {}
    for r in rows:
        quando = _parse(r.get("updated_at"))
        if quando is None or quando + backoff(int(r.get("tentativas") or 1)) <= now:
            por_org.setdefault(str(r["org_id"]), []).append(r)
    return por_org


def _drenar_org(client: Any, org_id: str, rows: list[dict], intake_fn: Callable[..., Any]) -> dict[str, int]:
    saida = {"tentados": 0, "ok": 0, "ainda_pendentes": 0, "erros": 0}
    for r in rows[:LOTE_POR_ORG]:
        saida["tentados"] += 1
        try:
            res = intake_fn(client, UUID(org_id), r["lead_id"])
        except Exception:
            saida["erros"] += 1
            logger.error("%s: lead=%s org=%s failed", JOB_NAME, r["lead_id"], org_id, exc_info=True)
            continue
        saida["ok" if res.get("status") != intake.ST_RETRY and res.get("status") != intake.ST_FALHOU else "ainda_pendentes"] += 1
    return saida


async def ad_lead_intake_retry_job(*, admin_factory: Any = None, intake_fn: Any = None, lease_fn: Any = None, now: Optional[datetime] = None) -> dict[str, Any]:
    """One drain pass over every org with due `pendente_retry` rows. Seams (None = real) so a test passes collaborators in."""
    from app.dependencies import get_admin_client
    from app.services import sync_lease

    client = (admin_factory or get_admin_client)()
    if client is None:
        logger.error("%s: no admin client -- skipping", JOB_NAME)
        return {}
    quando = now or datetime.now(timezone.utc)
    try:
        por_org = await asyncio.to_thread(elegiveis, client, quando)
    except Exception:
        logger.error("%s: reading the retry queue failed", JOB_NAME, exc_info=True)
        return {}
    relatorio: dict[str, Any] = {}
    for org_id, rows in por_org.items():
        lease_cm = (lease_fn or (lambda name: sync_lease.lease(client, name, ttl_seconds=LEASE_TTL_S)))(f"{JOB_NAME}:{org_id}")
        try:
            with lease_cm as got:
                if not got:
                    relatorio[org_id] = {"pulado": "lease_ocupada"}
                    continue
                relatorio[org_id] = await asyncio.to_thread(_drenar_org, client, org_id, rows, intake_fn or intake.intake_imovel_do_lead)
        except Exception:
            logger.error("%s: org=%s failed", JOB_NAME, org_id, exc_info=True)
            relatorio[org_id] = {"erro": True}
    if relatorio:
        logger.info("%s: %s", JOB_NAME, relatorio)
    return relatorio


def configure() -> None:
    """Register the interval job on the seed scheduler (import-time, before `start_scheduler()`; idempotent)."""
    seed_scheduler.register(JOB_NAME, ad_lead_intake_retry_job, seconds=INTERVALO_S, misfire_grace_time=_MISFIRE_GRACE)
    logger.info("%s configured: every %ds", JOB_NAME, INTERVALO_S)


__all__ = ["JOB_NAME", "ad_lead_intake_retry_job", "backoff", "configure", "elegiveis"]
