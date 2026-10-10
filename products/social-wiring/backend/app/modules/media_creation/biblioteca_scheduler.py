"""Biblioteca schedules (contract geracao 3.3 step 7).

* **Daily sync** (03:20 BRT): enqueue ``biblioteca.sync_perfil`` for every ``ativo`` profile that at
  least one marca references with ``auto_atualizar``; ``dedupe_key = sync:{perfil}:{YYYYMMDD}`` so a
  re-run the same day is a no-op. The ``biblioteca`` worker's claim gate keeps the queue idle while
  ``biblioteca_ingestao_habilitada`` is off, so enqueueing is always safe.
* **Pending sweep** (every 10 min), the delivery path the synchronous transcription hook cannot be:
  - a viral whose transcription settled (or never applied) but whose classification is still
    ``pendente`` gets its ``biblioteca.classificar`` job (``classificar:{id}:{YYYYMMDD}``);
  - a viral stuck in ``na_fila`` whose shared ``transcricoes`` row failed or was cancelled becomes
    ``falhou`` (and is then classified from the caption).

``NOC-REMEDIATE[biblioteca-retention]``: the 90-day purge of a profile with no references (contract
9.3) is NOT built until the owner confirms the 90 days; deleting a profile (endpoint 14) is the only
removal path today.

Registered at IMPORT time via ``configure()`` (same idiom as ``geracao_scheduler``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import batched

from app.dependencies import get_admin_client, get_scoped_admin_client
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.biblioteca_service import PERFIS, REFS, TRANSCRICOES, VIRAIS

logger = logging.getLogger(__name__)

SYNC_JOB_ID = "biblioteca_sync_diario"
SYNC_CRON = "20 3 * * *"
SWEEP_JOB_ID = "biblioteca_pendentes"
#: A minute set no other job here uses (geracao :02/:12.., cerebro :05/:15.., card_hub :17, imovel_hub :43).
SWEEP_CRON = "9,19,29,39,49,59 * * * *"

#: Transcription states from which classification may start.
CLASSIFICAVEL = ("nao_aplicavel", "concluida", "falhou", "grande_demais", "longa_demais", "sem_orcamento")
TRANSCRICAO_FALHA = ("falhou", "cancelada")


def _day(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%d")


async def enqueue_daily_syncs(db: Any, repo: JobRepository, *, now: Optional[datetime] = None) -> int:
    """Enqueue today's sync for every active, auto-updated profile. Returns how many were targeted."""
    refs = iter_paged_rows(
        lambda s, e: db.table(REFS).select("id,perfil_id").eq("modo", "perfil").eq("auto_atualizar", True)
        .order("id").range(s, e).execute().data
    )
    perfil_ids = sorted({str(r["perfil_id"]) for r in refs if r.get("perfil_id")})
    targeted = 0
    for chunk in batched(perfil_ids):
        rows = db.table(PERFIS).select("id").eq("status", "ativo").in_("id", chunk).execute().data or []
        for r in rows:
            await repo.enqueue(
                type="biblioteca.sync_perfil", payload={"perfil_id": str(r["id"])}, max_retries=2,
                dedupe_key=f"sync:{r['id']}:{_day(now)}",
            )
            targeted += 1
    return targeted


async def sweep_pendentes(db: Any, repo: JobRepository, *, now: Optional[datetime] = None) -> dict[str, int]:
    """See the module docstring. Returns ``{classificar, transcricoes_falhas}`` counts."""
    # 1. transcription rows that ended without the hook
    stuck = list(
        iter_paged_rows(
            lambda s, e: db.table(VIRAIS).select("id,transcricao_id").eq("transcricao_status", "na_fila")
            .order("id").range(s, e).execute().data
        )
    )
    failed_ids: set[str] = set()
    tids = sorted({str(v["transcricao_id"]) for v in stuck if v.get("transcricao_id")})
    for chunk in batched(tids):
        for t in db.table(TRANSCRICOES).select("id,status").in_("id", chunk).execute().data or []:
            if t.get("status") in TRANSCRICAO_FALHA:
                failed_ids.add(str(t["id"]))
    falhas = 0
    for v in stuck:
        if v.get("transcricao_id") and str(v["transcricao_id"]) in failed_ids:
            db.table(VIRAIS).update({"transcricao_status": "falhou"}).eq("id", str(v["id"])).eq(
                "transcricao_status", "na_fila").execute()
            falhas += 1
    # 2. classification still waiting although its transcription settled
    pend = iter_paged_rows(
        lambda s, e: db.table(VIRAIS).select("id").eq("e_viral", True).eq("classificacao_status", "pendente")
        .in_("transcricao_status", list(CLASSIFICAVEL)).order("id").range(s, e).execute().data
    )
    classificar = 0
    for v in pend:
        await repo.enqueue(
            type="biblioteca.classificar", payload={"viral_id": str(v["id"])}, max_retries=2,
            dedupe_key=f"classificar:{v['id']}:{_day(now)}",
        )
        classificar += 1
    return {"classificar": classificar, "transcricoes_falhas": falhas}


def _client():
    if get_admin_client() is None:
        logger.warning("biblioteca scheduler: no admin client — skipping run")
        return None
    return get_scoped_admin_client()


async def run_sync_diario(
    *, client: Optional[Callable[[], Any]] = None, repo: Optional[JobRepository] = None
) -> None:
    """Never raises (a scheduler job that throws can silently stop being scheduled)."""
    try:
        db = (client or _client)()
        if db is None:
            return
        n = await enqueue_daily_syncs(db, repo or geracao_jobs.make_jobs_repository(db))
        logger.info("biblioteca: sync diário enfileirado para %d perfis", n)
    except Exception as exc:  # noqa: BLE001
        logger.error("biblioteca sync diário falhou: %s", exc, exc_info=True)


async def run_sweep(
    *, client: Optional[Callable[[], Any]] = None, repo: Optional[JobRepository] = None
) -> None:
    try:
        db = (client or _client)()
        if db is None:
            return
        out = await sweep_pendentes(db, repo or geracao_jobs.make_jobs_repository(db))
        if any(out.values()):
            logger.info("biblioteca sweep: %s", out)
    except Exception as exc:  # noqa: BLE001
        logger.error("biblioteca sweep falhou: %s", exc, exc_info=True)


def configure() -> None:
    """Register both jobs on the seed-side scheduler. Idempotent; call before ``start_scheduler()``."""
    seed_scheduler.register(SYNC_JOB_ID, run_sync_diario, cron=SYNC_CRON)
    seed_scheduler.register(SWEEP_JOB_ID, run_sweep, cron=SWEEP_CRON)
    logger.info("biblioteca scheduler configured: sync diário (cron %r) + varredura (cron %r)", SYNC_CRON, SWEEP_CRON)


__all__ = [
    "SWEEP_CRON",
    "SWEEP_JOB_ID",
    "SYNC_CRON",
    "SYNC_JOB_ID",
    "configure",
    "enqueue_daily_syncs",
    "run_sweep",
    "run_sync_diario",
    "sweep_pendentes",
]
