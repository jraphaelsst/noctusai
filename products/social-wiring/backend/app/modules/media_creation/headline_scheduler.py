"""Daily automatic headline suggestions (Geração, BE-4): contract ``specs/geracao-contract.md`` 3.5.

At 06:10 (BRT -- the seed scheduler runs in America/Sao_Paulo) every marca that has a bio AND at
least one niche gets ONE ``sugestao_auto`` batch: the top ``headlines_sugeridas_por_dia_marca``
(5 -> 10 headlines) ``e_viral`` structures with a blueprint, ranked by ``score_viral`` (the marca's
Minha Biblioteca first, then niche overlap), skipping the virals this marca used in the last 30
days. A marca without a bio or niches is skipped and logged; no structures -> no batch, logged
(never an empty "completo"). The "Gerar sugestões agora" button shares this code path and the same
once-per-marca-per-day limit.

Registered at IMPORT time via ``configure()`` (same idiom as ``cerebro_scheduler`` /
``geracao_scheduler``). ``noctusai_lib.api.scheduler`` refuses to start unless
``NOCTUS_SCHEDULERS_ENABLED`` is set (deployed containers only), so locally the job registers and
never fires.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import PAGE_SIZE

from app.dependencies import get_admin_client, get_scoped_admin_client
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.headline_service import HeadlineError, HeadlineService

logger = logging.getLogger(__name__)

JOB_ID = "headline_sugestoes_diarias"
#: 06:10 in the scheduler's timezone (America/Sao_Paulo).
CRON = "10 6 * * *"
#: A run may still fire this late (a deploy restart spanning 06:10 must not skip the day).
MISFIRE_GRACE_SECONDS = 3600


def _client():
    if get_admin_client() is None:
        logger.warning("headline sugestões: sem cliente admin — rodada ignorada")
        return None
    return get_scoped_admin_client()


async def gerar_sugestoes_diarias(
    *,
    client: Optional[Callable[[], Any]] = None,
    repo: Optional[JobRepository] = None,
    cfg: Any = None,
) -> dict[str, int]:
    """Create today's suggestion batch for every eligible marca. Never raises (a scheduler job that
    throws can silently stop being scheduled); one marca's failure never stops the others. Returns
    ``{criados, ignorados, falhas}``. ``client`` / ``repo`` are the DI seams."""
    out = {"criados": 0, "ignorados": 0, "falhas": 0}
    if cfg is None:
        from app.config import settings as cfg
    if not cfg.geracao_worker_enabled:
        logger.info("headline sugestões: worker de geração desligado — rodada ignorada")
        return out
    try:
        db = (client or _client)()
        if db is None:
            return out
        queue = repo or geracao_jobs.make_jobs_repository(db)
        perfis = list(iter_paged_rows(
            lambda s, e: db.table("cs_marca_perfil").select("marca_id,org_id,bio,nichos")
            .order("marca_id").range(s, e).execute().data,
            page_size=PAGE_SIZE, id_key="marca_id", label="cs_marca_perfil sugestões",
        ))
        for p in perfis:
            if not (p.get("bio") or "").strip() or not p.get("nichos"):
                logger.info("headline sugestões: marca %s sem bio ou nicho — ignorada", p["marca_id"])
                out["ignorados"] += 1
                continue
            try:
                svc = HeadlineService(db, p["org_id"], None, cfg=cfg, jobs=queue)
                await svc.criar_sugestao(str(p["marca_id"]))
                out["criados"] += 1
            except HeadlineError as exc:
                # 429 (already today) / 409 (no structures) are expected steady states, not failures
                logger.info("headline sugestões: marca %s ignorada: %s", p["marca_id"], exc.detail)
                out["ignorados"] += 1
            except Exception as exc:  # noqa: BLE001 - one marca must not stop the run
                logger.error("headline sugestões: marca %s falhou: %s", p["marca_id"], exc, exc_info=True)
                out["falhas"] += 1
        if out["criados"] or out["falhas"]:
            logger.info("headline sugestões: %s", out)
    except Exception as exc:  # noqa: BLE001 - scheduler job must not die
        logger.error("headline sugestões: rodada falhou: %s", exc, exc_info=True)
    return out


async def _run() -> None:
    await gerar_sugestoes_diarias()


def configure() -> None:
    """Register the daily job on the seed-side scheduler. Idempotent. Must run at import time,
    before ``start_scheduler()`` fires in ``app/lifespan.py``."""
    seed_scheduler.register(JOB_ID, _run, cron=CRON, misfire_grace_time=MISFIRE_GRACE_SECONDS)
    logger.info("headline scheduler configured: sugestões diárias (cron %r, BRT)", CRON)


__all__ = ["CRON", "JOB_ID", "MISFIRE_GRACE_SECONDS", "configure", "gerar_sugestoes_diarias"]
