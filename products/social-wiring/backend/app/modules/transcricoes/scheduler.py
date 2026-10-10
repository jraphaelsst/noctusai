"""Retention + safety-net sweep for transcriptions (LGPD: voice is personal data).

Every 15 minutes (certidoes idiom: registered at IMPORT time via ``configure()``,
before ``start_scheduler()`` fires in ``app/lifespan.py``):

1. in-flight jobs older than 2 h -> ``falhou`` (``tempo_esgotado``) + minutes refunded;
2. audio of failed jobs deleted after 72 h; audio of a finished job whose immediate
   delete failed is retried;
3. transcripts older than 7 days are purged (``texto`` -> NULL) — the saved copy,
   if any, lives in the consumer's own record.

Never raises: a scheduler job that throws can silently stop being scheduled.
``noctusai_lib.api.scheduler`` only fires in deployed containers
(``NOCTUS_SCHEDULERS_ENABLED``); locally the job registers and never runs.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.integrations.storage import StorageBackend

from app.dependencies import get_admin_client
from app.modules.transcricoes.deps import get_transcricao_storage
from app.modules.transcricoes.service import (
    IN_FLIGHT,
    TABLE,
    apagar_audio,
    iso,
    marcar_falha,
    now,
)

logger = logging.getLogger(__name__)

JOB_ID = "transcricoes_retention_sweep"
#: :07 / :22 / :37 / :52 — minutes no other sweep in this product uses.
CRON = "7,22,37,52 * * * *"

STALE_JOB = timedelta(hours=2)
FAILED_AUDIO_TTL = timedelta(hours=72)
TEXT_TTL = timedelta(days=7)
#: A finished job's audio is deleted inline; one still around after this lost the delete.
LEFTOVER_AUDIO_GRACE = timedelta(hours=1)
BATCH = 200


async def sweep(db: Any, storage: StorageBackend) -> dict[str, int]:
    """Run the three passes. Returns counts (for logs / tests)."""
    moment = now()
    out = {"expiradas": 0, "audios_apagados": 0, "textos_purgados": 0}

    stale = (
        db.table(TABLE).select("id").in_("status", list(IN_FLIGHT))
        .lt("criado_em", iso(moment - STALE_JOB)).limit(BATCH).execute().data or []
    )
    for r in stale:
        if marcar_falha(db, r["id"], "tempo_esgotado", reembolsar=True):
            out["expiradas"] += 1

    leftovers = (
        db.table(TABLE).select("id,storage_path,audio_apagado_em,status")
        .is_("audio_apagado_em", "null").in_("status", ["falhou", "cancelada"])
        .lt("concluido_em", iso(moment - FAILED_AUDIO_TTL)).limit(BATCH).execute().data or []
    )
    leftovers += (
        db.table(TABLE).select("id,storage_path,audio_apagado_em,status")
        .is_("audio_apagado_em", "null").eq("status", "concluida")
        .lt("concluido_em", iso(moment - LEFTOVER_AUDIO_GRACE)).limit(BATCH).execute().data or []
    )
    for r in leftovers:
        if await apagar_audio(db, storage, r):
            out["audios_apagados"] += 1

    purgaveis = (
        db.table(TABLE).select("id").eq("status", "concluida")
        .lt("concluido_em", iso(moment - TEXT_TTL)).limit(BATCH).execute().data or []
    )
    for r in purgaveis:
        # Rows already purged have texto NULL; re-nulling is a harmless no-op.
        db.table(TABLE).update({"texto": None}).eq("id", r["id"]).execute()
        out["textos_purgados"] += 1
    return out


def _db():
    return get_admin_client()


async def run_sweep(
    *, db: Optional[Callable[[], Any]] = None, storage: Optional[Callable[[], StorageBackend]] = None
) -> None:
    """The scheduled entry. ``db`` / ``storage`` are DI seams so a test drives the
    sweep against a mock DB + FakeStorageBackend and asserts on the ROWS touched."""
    try:
        client = (db or _db)()
        if client is None:
            logger.warning("transcricoes sweep: no admin client — skipping run")
            return
        moved = await sweep(client, (storage or get_transcricao_storage)())
        if any(moved.values()):
            logger.info("transcricoes sweep: %s", moved)
    except Exception as exc:  # noqa: BLE001 - scheduler job must not die
        logger.error("transcricoes sweep: run failed: %s", exc, exc_info=True)


def configure() -> None:
    """Register the sweep on the seed-side scheduler. Idempotent."""
    seed_scheduler.register(JOB_ID, run_sweep, cron=CRON)
    logger.info("transcricoes scheduler configured: retention sweep (cron %r)", CRON)


__all__ = ["CRON", "JOB_ID", "configure", "run_sweep", "sweep"]
