"""Scheduled LGPD retention sweeps for the two surfaces that had a purge
primitive but no schedule (migration 111): `imovel_documentos` (via
`imovel_hub.documentos_service.STORE.varrer_expirados`) and
`matricula_extracoes.texto_extraido` (via
`matriculas.estrutura_service.purgar_texto_expirado`). The `cliente` and
`atendimento` surfaces are already scheduled by `card_hub`.

Registered at 03:40 America/Sao_Paulo — a quiet hour, off the :00/:30 marks
the other jobs use. Per-org, per-surface failures are logged and the walk
continues; a bug never de-registers the job.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.integrations.persistence import iter_paged_rows

from app.services import table_reads

logger = logging.getLogger(__name__)

JOB_ID = "lgpd_retention_sweep_imovel_matricula"
CRON = "40 3 * * *"


def _orgs(client: Any, table_name: str) -> list[UUID]:
    def fetch_page(start: int, end: int):
        return (
            table_reads.table(client, table_name)
            .select("org_id")
            .order("id")
            .range(start, end)
            .execute()
        ).data

    vistos: set[str] = set()
    for row in iter_paged_rows(fetch_page, label=f"{table_name} org_id scan"):
        if row.get("org_id"):
            vistos.add(str(row["org_id"]))
    return [UUID(o) for o in sorted(vistos)]


def run_sweep(client: Any = None) -> dict[str, int]:
    """One pass over every org, both surfaces. Returns the removed counts."""
    from app.modules.card_hub.deps import get_card_hub_client
    from app.modules.imovel_hub import documentos_service as imovel_docs
    from app.modules.matriculas import estrutura_service

    db = client if client is not None else get_card_hub_client()
    totais = {"imovel_documentos": 0, "matricula_textos": 0, "erros": 0}
    for org_id in _orgs(db, imovel_docs.TABLE):
        try:
            totais["imovel_documentos"] += imovel_docs.STORE.varrer_expirados(db, org_id)
        except Exception:
            totais["erros"] += 1
            logger.error("retention sweep: imovel_documentos org=%s failed", org_id, exc_info=True)
    for org_id in _orgs(db, estrutura_service.EXTRACOES_TABLE):
        try:
            totais["matricula_textos"] += estrutura_service.purgar_texto_expirado(db, org_id)
        except Exception:
            totais["erros"] += 1
            logger.error("retention sweep: matricula_extracoes org=%s failed", org_id, exc_info=True)
    logger.info("lgpd retention sweep (imovel/matricula): %s", totais)
    return totais


def retention_sweep_job(*, run_fn: Any = None) -> None:
    """Scheduler entrypoint — never raises (test seam: `run_fn`)."""
    try:
        (run_fn or run_sweep)()
    except Exception:
        logger.error("lgpd retention sweep (imovel/matricula) failed", exc_info=True)


def configure() -> None:
    seed_scheduler.register(JOB_ID, retention_sweep_job, cron=CRON)
    logger.info("lgpd retention sweep configured: %s at cron %r", JOB_ID, CRON)


__all__ = ["CRON", "JOB_ID", "configure", "retention_sweep_job", "run_sweep"]
