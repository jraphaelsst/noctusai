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

* **Retention + orphan-blob sweep** (daily 04:40 BRT, LGPD contract 9.3): a monitored profile is a
  third party whose posts, voice and picture we hold, so data nobody uses is erased.
  - A profile that is ``pausado`` or referenced by no marca (neither a ``perfil`` reference nor a
    ``video`` reference to one of its virais) is stamped ``inativo_desde`` the first sweep that sees
    it so; the stamp is cleared the moment it is in use again.
  - After ``biblioteca_retencao_dias`` (config, default 90 -- the owner validates the number) it is
    PURGED through the same :func:`purgar_perfil` the delete endpoint uses: caption, transcript,
    blueprint, thumbnails, profile picture / name / followers -- rows and blobs.
  - The orphan sweep deletes every ``sw-biblioteca/{org}/{perfil}/`` prefix whose profile no longer
    exists. It is the RETRY for a blob delete that failed (logged, never fatal) and the cleanup for a
    sync that was still uploading when its profile was deleted.

Registered at IMPORT time via ``configure()`` (same idiom as ``geracao_scheduler``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.persistence.table_reads import batched

from app.dependencies import get_admin_client, get_scoped_admin_client
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.biblioteca_service import (
    BUCKET,
    PERFIS,
    REFS,
    TRANSCRICOES,
    VIRAIS,
    purgar_perfil,
)

logger = logging.getLogger(__name__)

SYNC_JOB_ID = "biblioteca_sync_diario"
SYNC_CRON = "20 3 * * *"
SWEEP_JOB_ID = "biblioteca_pendentes"
#: A minute set no other job here uses (geracao :02/:12.., cerebro :05/:15.., card_hub :17, imovel_hub :43).
SWEEP_CRON = "9,19,29,39,49,59 * * * *"
RETENCAO_JOB_ID = "biblioteca_retencao"
RETENCAO_CRON = "40 4 * * *"
#: Upper bound of one ``list_keys`` page (the storage seam has no cursor): more orgs / profiles than this
#: in the bucket are reached over successive daily runs as earlier orphans are deleted.
LISTA_MAX = 1000

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


# ── LGPD retention + orphan blobs ────────────────────────────────────────────


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _perfis_referenciados(db: Any) -> set[str]:
    """Profile ids some marca still uses: a ``perfil`` reference, or a ``video`` reference to one of its virais."""
    usados: set[str] = set()
    video_ids: list[str] = []
    for r in iter_paged_rows(
        lambda s, e: db.table(REFS).select("id,modo,perfil_id,viral_id").order("id").range(s, e).execute().data
    ):
        if r.get("modo") == "perfil" and r.get("perfil_id"):
            usados.add(str(r["perfil_id"]))
        elif r.get("modo") == "video" and r.get("viral_id"):
            video_ids.append(str(r["viral_id"]))
    for chunk in batched(sorted(set(video_ids))):
        for v in db.table(VIRAIS).select("id,perfil_id").in_("id", chunk).execute().data or []:
            usados.add(str(v["perfil_id"]))
    return usados


async def purgar_expirados(
    db: Any, storage: StorageBackend, *, dias: int, now: Optional[datetime] = None
) -> dict[str, int]:
    """Stamp / clear ``inativo_desde`` and purge the profiles idle for ``dias`` days. Returns
    ``{marcados, reativados, purgados, blobs_falhos}``."""
    agora = now or datetime.now(timezone.utc)
    usados = _perfis_referenciados(db)
    out = {"marcados": 0, "reativados": 0, "purgados": 0, "blobs_falhos": 0}
    perfis = list(
        iter_paged_rows(
            lambda s, e: db.table(PERFIS).select("id,org_id,status,foto_path,inativo_desde")
            .order("id").range(s, e).execute().data
        )
    )
    for p in perfis:
        inativo = p.get("status") == "pausado" or str(p["id"]) not in usados
        desde = _parse_ts(p.get("inativo_desde"))
        if not inativo:
            if desde is not None:
                db.table(PERFIS).update({"inativo_desde": None}).eq("id", str(p["id"])).execute()
                out["reativados"] += 1
        elif desde is None:
            db.table(PERFIS).update({"inativo_desde": agora.isoformat()}).eq("id", str(p["id"])).execute()
            out["marcados"] += 1
        elif agora - desde >= timedelta(days=dias):
            out["blobs_falhos"] += await purgar_perfil(db, storage, str(p["org_id"]), p)
            out["purgados"] += 1
    return out


def _segmento(chave: str, n: int) -> Optional[str]:
    """The ``n``-th path segment of a listed key (Supabase lists a "folder" as a bare name, the Fake lists
    full keys -- both reduce to the same segments)."""
    partes = [x for x in chave.split("/") if x]
    return partes[n] if len(partes) > n else None


async def varrer_blobs_orfaos(db: Any, storage: StorageBackend) -> dict[str, int]:
    """Delete every ``{org}/{perfil}/`` prefix of ``sw-biblioteca`` whose profile row no longer exists.
    Returns ``{orfaos, blobs_apagados, blobs_falhos}``."""
    out = {"orfaos": 0, "blobs_apagados": 0, "blobs_falhos": 0}
    orgs = sorted({o for k in await storage.list_keys(bucket=BUCKET, prefix="", limit=LISTA_MAX) if (o := _segmento(k, 0))})
    for org in orgs:
        perfis = sorted({
            p for k in await storage.list_keys(bucket=BUCKET, prefix=f"{org}/", limit=LISTA_MAX)
            if (p := _segmento(k, 1))
        })
        vivos: set[str] = set()
        for chunk in batched(perfis):
            vivos |= {str(r["id"]) for r in db.table(PERFIS).select("id").in_("id", chunk).execute().data or []}
        for perfil in perfis:
            if perfil in vivos:
                continue
            out["orfaos"] += 1
            for key in await storage.list_keys(bucket=BUCKET, prefix=f"{org}/{perfil}/", limit=LISTA_MAX):
                try:
                    await storage.delete(bucket=BUCKET, key=key)
                    out["blobs_apagados"] += 1
                except Exception:  # noqa: BLE001 - retried by tomorrow's sweep
                    out["blobs_falhos"] += 1
                    logger.warning("biblioteca: blob órfão não apagado key=%s", key, exc_info=True)
    return out


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


def _storage() -> StorageBackend:
    from app.modules.certidoes.deps import storage_for

    return storage_for(get_admin_client())


async def run_retencao(
    *, client: Optional[Callable[[], Any]] = None, storage: Optional[StorageBackend] = None, dias: Optional[int] = None,
) -> None:
    """Never raises. Purge first, then the orphan sweep (so the purge's own failed blobs are retried the same night)."""
    try:
        db = (client or _client)()
        if db is None:
            return
        from app.config import settings

        st = storage or _storage()
        purga = await purgar_expirados(db, st, dias=int(dias if dias is not None else settings.biblioteca_retencao_dias))
        orfaos = await varrer_blobs_orfaos(db, st)
        if any(purga.values()) or any(orfaos.values()):
            logger.info("biblioteca retenção: %s órfãos: %s", purga, orfaos)
    except Exception as exc:  # noqa: BLE001
        logger.error("biblioteca retenção falhou: %s", exc, exc_info=True)


def configure() -> None:
    """Register both jobs on the seed-side scheduler. Idempotent; call before ``start_scheduler()``."""
    seed_scheduler.register(SYNC_JOB_ID, run_sync_diario, cron=SYNC_CRON)
    seed_scheduler.register(SWEEP_JOB_ID, run_sweep, cron=SWEEP_CRON)
    seed_scheduler.register(RETENCAO_JOB_ID, run_retencao, cron=RETENCAO_CRON)
    logger.info(
        "biblioteca scheduler configured: sync diário (cron %r) + varredura (cron %r) + retenção (cron %r)",
        SYNC_CRON, SWEEP_CRON, RETENCAO_CRON,
    )


__all__ = [
    "RETENCAO_CRON",
    "RETENCAO_JOB_ID",
    "purgar_expirados",
    "run_retencao",
    "varrer_blobs_orfaos",
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
