"""Biblioteca schedules (contract geracao 3.3 step 7).

* **Daily sync** (03:20 BRT): the library is PLATFORM-WIDE (migration 351): enqueue ``biblioteca.sync_perfil`` for every
  platform profile with ``monitorar = true`` that is ``ativo`` (or waiting on a budget / credential);
  ``dedupe_key = sync:{perfil}:{YYYYMMDD}`` so a re-run the same day is a no-op. The ``biblioteca`` worker's claim gate keeps
  the queue idle while ``biblioteca_ingestao_habilitada`` is off, so enqueueing is always safe.
* **Pending sweep** (every 10 min), the delivery path the synchronous transcription hook cannot be:
  - a viral (``e_viral``, or one an admin added by link) whose transcription settled (or never applied) but whose
    classification is still ``pendente`` gets its ``biblioteca.classificar`` job (``classificar:{id}:{YYYYMMDD}``);
  - a viral stuck in ``na_fila`` whose shared ``transcricoes`` row failed or was cancelled becomes
    ``falhou`` (and is then classified from the caption).

* **Retention + orphan-blob sweep** (daily 04:40 BRT, LGPD contract 9.3): a monitored profile is a
  third party whose posts, voice and picture we hold, so data nobody uses is erased.
  - A profile that is ``pausado`` or referenced by no marca (neither a ``perfil`` reference nor a
    ``video`` reference to one of its virais) is stamped ``inativo_desde`` the first sweep that sees
    it so; the stamp is cleared the moment it is in use again -- UNLESS it is RETAINED: it has >= 1 
    ``ativa`` Estrutura (the published, curated derived data; EST-5 legal review 2026-11-16 -- a draft never exempts, and
    ``monitorar = false`` alone no longer does either). A retained profile is never purged as a profile, but its viral media / transcripts /
    thumbnails are still erased by age (:func:`purgar_virais_antigos`), except the videos a marca selected, and a retained
    library-only profile (``monitorar = false``) is MINIMISED: photo + follower count dropped (:func:`minimizar_perfil`).
  - After ``biblioteca_retencao_dias`` (config, default 90 -- the owner validates the number) an unused,
    non-retained profile is PURGED through the same :func:`purgar_perfil` the delete endpoint uses: caption, transcript,
    blueprint, thumbnails, profile picture / name / followers -- rows and blobs.
  - The orphan sweep deletes every ``sw-biblioteca/{org|platform}/{perfil}/`` prefix whose profile no longer
    exists. It is the RETRY for a blob delete that failed (logged, never fatal) and the cleanup for a
    sync that was still uploading when its profile was deleted. Only UUID (or ``platform``) segments are profile
    prefixes: any other segment is skipped EXPLICITLY and counted (``segmentos_ignorados``, logged -- security review F1),
    and ``importacoes/`` (the Estruturas load documents) has its own sweep, :func:`varrer_blobs_importacao`.
  - **24-month-unused review** (owner decision 2026-11-15): an ``ativa`` Estrutura nobody used / edited / published for
    :data:`REVISAO_DESUSO_MESES` months is FLAGGED for admin review (never archived) through ``cs_estruturas_revisao_desuso``;
    the per-run counts are always logged.

Registered at IMPORT time via ``configure()`` (same idiom as ``geracao_scheduler``).
"""
from __future__ import annotations

import logging
import uuid
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
    CONTEXTO_TIPO,
    ESTRUTURAS,
    PERFIS,
    REFS,
    TRANSCRICOES,
    VIRAIS,
    apagar_transcricoes,
    minimizar_perfil,
    purgar_perfil,
    registrar_evento,
)
from app.modules.media_creation.services.estruturas_import import IMPORTACOES_T, PREFIXO_BLOB, SIMULACAO_VALIDADE_HORAS
from app.modules.media_creation.services.biblioteca_fonte import PREFIXO_PLATAFORMA

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
#: The owner's 24-month-unused review window (decision 2026-11-15), in months.
REVISAO_DESUSO_MESES = 24
#: Days an Estruturas load document may stay in the bucket while its lote is ``em_andamento`` (stuck) before the sweep
#: deletes it; a finished / failed / unknown lote's document goes at the next run, a ``simulada`` one after its 24 h validity.
#: NOC-REMEDIATE[cs-importacao-blob-ttl-setting]: a module constant because config.py is not this slice's file; move it to
#: ``settings`` (``estruturas_importacao_blob_dias``) with the next config change -- 2026-11-30.
IMPORTACAO_BLOB_TTL_DIAS = 7

#: Transcription states from which classification may start.
CLASSIFICAVEL = ("nao_aplicavel", "concluida", "falhou", "grande_demais", "longa_demais", "sem_orcamento")
TRANSCRICAO_FALHA = ("falhou", "cancelada")


def _day(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%d")


async def enqueue_daily_syncs(db: Any, repo: JobRepository, *, now: Optional[datetime] = None) -> int:
    """Enqueue today's sync for every platform profile with ``monitorar = true`` that is active (or only waiting on a
    budget / credential). Returns how many were targeted."""
    rows = iter_paged_rows(
        lambda s, e: db.table(PERFIS).select("id").eq("monitorar", True)
        .in_("status", ["ativo", "sem_orcamento", "sem_credencial"]).order("id").range(s, e).execute().data
    )
    targeted = 0
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
    # Two plain equality queries (not one `or`): a viral video, and a video an admin added by link (chosen by hand, so
    # analysed whatever its viral score). Deduped by id.
    pend_ids: dict[str, None] = {}
    for coluna, valor in (("e_viral", True), ("origem_inclusao", "link_manual")):
        for v in iter_paged_rows(
            lambda s, e, coluna=coluna, valor=valor: db.table(VIRAIS).select("id").eq(coluna, valor)
            .eq("classificacao_status", "pendente").in_("transcricao_status", list(CLASSIFICAVEL))
            .order("id").range(s, e).execute().data
        ):
            pend_ids[str(v["id"])] = None
    pend = [{"id": i} for i in pend_ids]
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


def _perfis_de_marcas(db: Any) -> set[str]:
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


def _perfis_selecionados(db: Any) -> set[str]:
    """Profiles a marca selected AS A WHOLE (``perfil`` reference): their videos never expire by age."""
    return {
        str(r["perfil_id"]) for r in iter_paged_rows(
            lambda s, e: db.table(REFS).select("id,perfil_id").eq("modo", "perfil").order("id").range(s, e).execute().data
        ) if r.get("perfil_id")
    }


def _perfis_retidos(db: Any) -> set[str]:
    """Profiles exempt from the unreferenced purge: those with >= 1 ``ativa`` (PUBLISHED, curated) Estrutura.

    Only ``ativa`` exempts (EST-5 legal review 2026-11-16): a ``rascunho`` -- above all an AI ``viral_auto`` draft -- is
    uncurated text derived from a third party's video and must not keep the creator's profile alive; ``arquivada`` never did.
    (The alternative "anything but an auto-draft" would let an unpublished admin draft pin a profile forever and would not
    match the ROPA/LIA wording, which says only ``ativa``.) A brand selection is handled by :func:`_perfis_de_marcas`;
    ``monitorar = false`` alone exempts nothing (owner decision 2026-11-15, #4)."""
    return {
        str(r["perfil_id"]) for r in iter_paged_rows(
            lambda s, e: db.table(ESTRUTURAS).select("id,perfil_id").eq("status", "ativa")
            .order("id").range(s, e).execute().data
        ) if r.get("perfil_id")
    }


def _viral_ids_selecionados(db: Any) -> set[str]:
    return {
        str(r["viral_id"]) for r in iter_paged_rows(
            lambda s, e: db.table(REFS).select("id,viral_id").eq("modo", "video").order("id").range(s, e).execute().data
        ) if r.get("viral_id")
    }


async def purgar_virais_antigos(
    db: Any, storage: StorageBackend, perfil: dict[str, Any], *, dias: int, protegidos: set[str],
    now: Optional[datetime] = None,
) -> dict[str, int]:
    """For a RETAINED profile: erase the videos stored longer than ``dias`` ago (thumbnail blob, library transcript, row; the
    Estruturas derived from them keep living -- ``cs_estruturas.viral_id`` is ``ON DELETE SET NULL``), except the videos a
    marca selected. Each erased video leaves a content-free ``excluido`` event. Returns ``{virais, blobs_falhos}``."""
    agora = now or datetime.now(timezone.utc)
    corte = (agora - timedelta(days=dias)).isoformat()
    pid = str(perfil["id"])
    velhos = [
        v for v in iter_paged_rows(
            lambda s, e: db.table(VIRAIS).select("id,thumbnail_path").eq("perfil_id", pid).lt("created_at", corte)
            .order("id").range(s, e).execute().data
        ) if str(v["id"]) not in protegidos
    ]
    out = {"virais": 0, "blobs_falhos": 0}
    if not velhos:
        return out
    for v in velhos:
        if v.get("thumbnail_path"):
            try:
                await storage.delete(bucket=BUCKET, key=v["thumbnail_path"])
            except Exception:  # noqa: BLE001 - the row goes anyway; the orphan sweep retries the prefix listing
                out["blobs_falhos"] += 1
                logger.warning("biblioteca: thumbnail antigo não apagado key=%s", v["thumbnail_path"], exc_info=True)
    # transcripts go through the transcription organ (recording + text, in-flight jobs included -- F2)
    t = await apagar_transcricoes(db, storage, [str(v["id"]) for v in velhos])
    out["blobs_falhos"] += t["audios_falhos"]
    for chunk in batched([str(v["id"]) for v in velhos]):
        db.table(VIRAIS).delete().in_("id", chunk).execute()
    for v in velhos:
        registrar_evento(db, perfil_id=pid, tipo="excluido", ator_id=None, ator_tipo="sistema", viral_id=str(v["id"]))
        out["virais"] += 1
    return out


async def purgar_expirados(
    db: Any, storage: StorageBackend, *, dias: int, now: Optional[datetime] = None
) -> dict[str, int]:
    """Stamp / clear ``inativo_desde`` and purge the profiles idle for ``dias`` days; erase the old videos of retained
    profiles; erase the old videos of retained profiles and minimise the retained library-only ones. Returns
    ``{marcados, reativados, purgados, blobs_falhos, virais_antigos, minimizados}``."""
    agora = now or datetime.now(timezone.utc)
    de_marcas = _perfis_de_marcas(db)
    retidos = _perfis_retidos(db)
    selecionados = _viral_ids_selecionados(db)
    inteiros = _perfis_selecionados(db)
    out = {"marcados": 0, "reativados": 0, "purgados": 0, "blobs_falhos": 0, "virais_antigos": 0, "minimizados": 0}
    perfis = list(
        iter_paged_rows(
            lambda s, e: db.table(PERFIS).select("id,org_id,status,foto_path,seguidores,monitorar,inativo_desde")
            .order("id").range(s, e).execute().data
        )
    )
    for p in perfis:
        pid = str(p["id"])
        retido = pid in retidos
        inativo = not retido and (p.get("status") == "pausado" or pid not in de_marcas)
        desde = _parse_ts(p.get("inativo_desde"))
        if retido and pid not in inteiros:
            # Retained (Estruturas / library-only) and not selected whole by a marca: its media still expires by age
            # (the videos a marca selected one by one are protected inside).
            r = await purgar_virais_antigos(db, storage, p, dias=dias, protegidos=selecionados, now=agora)
            out["virais_antigos"] += r["virais"]
            out["blobs_falhos"] += r["blobs_falhos"]
        if retido and p.get("monitorar") is False and (p.get("foto_path") or p.get("seguidores") is not None):
            # Kept only for its Estruturas and never scraped: it drops photo + follower count (decision #4).
            if await minimizar_perfil(db, storage, pid, ator_tipo="sistema"):
                out["minimizados"] += 1
        if not inativo:
            if desde is not None:
                db.table(PERFIS).update({"inativo_desde": None}).eq("id", pid).execute()
                out["reativados"] += 1
        elif desde is None:
            db.table(PERFIS).update({"inativo_desde": agora.isoformat()}).eq("id", pid).execute()
            out["marcados"] += 1
        elif agora - desde >= timedelta(days=dias):
            # Re-check right before the destructive step: an Estrutura published since the scan keeps the profile.
            tem = db.table(ESTRUTURAS).select("id").eq("perfil_id", pid).eq("status", "ativa").limit(1).execute().data
            if tem:
                continue
            r = await purgar_perfil(
                db, storage, p, ator_tipo="sistema", tipo_evento="excluido", apagar_estruturas=True,
            )
            out["blobs_falhos"] += r["blobs_falhos"]
            out["purgados"] += 1
    return out


def _segmento(chave: str, n: int) -> Optional[str]:
    """The ``n``-th path segment of a listed key (Supabase lists a "folder" as a bare name, the Fake lists
    full keys -- both reduce to the same segments)."""
    partes = [x for x in chave.split("/") if x]
    return partes[n] if len(partes) > n else None


def _e_uuid(valor: Optional[str]) -> bool:
    if not valor:
        return False
    try:
        uuid.UUID(valor)
    except ValueError:
        return False
    return True


async def varrer_blobs_orfaos(db: Any, storage: StorageBackend) -> dict[str, int]:
    """Delete every ``{org|platform}/{perfil}/`` prefix of ``sw-biblioteca`` whose profile row no longer exists.

    Only a UUID (or the literal ``platform``) first segment and a UUID second segment name a profile prefix. Anything else
    in the bucket -- the ``importacoes/`` documents of the Estruturas load (their own sweep), a stray object -- is skipped
    EXPLICITLY: counted in ``segmentos_ignorados`` and logged, never silently dropped and never cast to a UUID column
    (the 22P02 crash of security review F1).
    Returns ``{orfaos, blobs_apagados, blobs_falhos, segmentos_ignorados}``."""
    out = {"orfaos": 0, "blobs_apagados": 0, "blobs_falhos": 0, "segmentos_ignorados": 0}
    raiz = sorted({o for k in await storage.list_keys(bucket=BUCKET, prefix="", limit=LISTA_MAX) if (o := _segmento(k, 0))})
    orgs: list[str] = []
    for o in raiz:
        if o == PREFIXO_PLATAFORMA or _e_uuid(o):
            orgs.append(o)
        elif o != PREFIXO_BLOB.rstrip("/"):  # the load documents have their own sweep: not an unknown segment
            out["segmentos_ignorados"] += 1
    for org in orgs:
        candidatos = sorted({
            p for k in await storage.list_keys(bucket=BUCKET, prefix=f"{org}/", limit=LISTA_MAX)
            if (p := _segmento(k, 1))
        })
        perfis = [p for p in candidatos if _e_uuid(p)]
        out["segmentos_ignorados"] += len(candidatos) - len(perfis)
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
    if out["segmentos_ignorados"]:
        logger.warning("biblioteca: varredura de órfãos ignorou %d segmento(s) que não são prefixo de perfil", out["segmentos_ignorados"])
    return out


async def varrer_blobs_importacao(
    db: Any, storage: StorageBackend, *, dias: int = IMPORTACAO_BLOB_TTL_DIAS, now: Optional[datetime] = None,
) -> dict[str, int]:
    """Delete the stored Estruturas load documents (``importacoes/{lote}.json``) nobody needs any more (security review F1).

    The worker deletes the document itself when the job ends; this is the net for every path that skipped it (a queue-level
    dead letter, a crash, a simulation never applied). A document goes when its lote is ``concluida`` / ``falhou`` /
    unknown, ``simulada`` and older than its 24 h validity, or still ``em_andamento`` after ``dias`` days (stuck).
    A key that is not ``{uuid}.json`` is counted in ``segmentos_ignorados`` and logged, never cast to a UUID.
    Returns ``{apagados, falhos, segmentos_ignorados}``."""
    agora = now or datetime.now(timezone.utc)
    out = {"apagados": 0, "falhos": 0, "segmentos_ignorados": 0}
    chaves: dict[str, str] = {}
    for k in await storage.list_keys(bucket=BUCKET, prefix=PREFIXO_BLOB, limit=LISTA_MAX):
        nome = _segmento(k, 1)
        lote = nome[: -len(".json")] if nome and nome.endswith(".json") else None
        if _e_uuid(lote):
            chaves[str(lote)] = f"{PREFIXO_BLOB}{nome}"
        else:
            out["segmentos_ignorados"] += 1
    lotes: dict[str, dict[str, Any]] = {}
    for chunk in batched(sorted(chaves)):
        for r in db.table(IMPORTACOES_T).select("id,status,created_at").in_("id", chunk).execute().data or []:
            lotes[str(r["id"])] = r
    for lote, chave in sorted(chaves.items()):
        row = lotes.get(lote)
        criado = _parse_ts(row.get("created_at")) if row else None
        if row is None or row["status"] in ("concluida", "falhou"):
            apagar = True
        elif row["status"] == "simulada":
            apagar = criado is not None and agora - criado >= timedelta(hours=SIMULACAO_VALIDADE_HORAS)
        else:  # em_andamento: only a stuck one
            apagar = criado is not None and agora - criado >= timedelta(days=dias)
        if not apagar:
            continue
        try:
            await storage.delete(bucket=BUCKET, key=chave)
            out["apagados"] += 1
        except Exception:  # noqa: BLE001 - retried by tomorrow's sweep
            out["falhos"] += 1
            logger.warning("biblioteca: documento de importação não apagado key=%s", chave, exc_info=True)
    if out["segmentos_ignorados"]:
        logger.warning("biblioteca: varredura de importações ignorou %d chave(s) fora do formato {uuid}.json", out["segmentos_ignorados"])
    return out


def expirar_rascunhos_automaticos(db: Any, *, dias: int) -> dict[str, int]:
    """EST-5 legal review: a ``viral_auto`` draft neither published nor edited for ``dias`` (``biblioteca_retencao_dias``;
    keyed on ``updated_at``, so a draft an admin is reviewing is never lost) is deleted by ``cs_estruturas_rascunhos_expirar``
    with a content-free ``rascunho_expirado`` event each. Always logs the count.

    Its failure (e.g. migration 351 not applied yet) must not skip the other nightly sweeps: it is logged at ERROR with the
    exception type and counted (``erros``) in the run summary -- never a silent pass. Returns ``{expiradas, erros}``."""
    try:
        res = db.rpc("cs_estruturas_rascunhos_expirar", {"p_dias": int(dias)}).execute()
    except Exception as exc:  # noqa: BLE001 - counted + logged at ERROR; the orphan / import sweeps still run
        logger.error("biblioteca: expiração de rascunhos automáticos falhou (%s)", type(exc).__name__)
        return {"expiradas": 0, "erros": 1}
    data = getattr(res, "data", None)
    data = data[0] if isinstance(data, list) and data else data
    out = {"expiradas": int((data or {}).get("expiradas") or 0), "erros": 0}
    logger.info("biblioteca: %d rascunho(s) automático(s) expirado(s) (> %d dias sem publicar)", out["expiradas"], dias)
    return out


def sinalizar_revisao_por_desuso(db: Any, *, meses: int = REVISAO_DESUSO_MESES) -> dict[str, int]:
    """The 24-month-unused review (owner decision 2026-11-15): ONE ``cs_estruturas_revisao_desuso`` call flags every ``ativa``
    Estrutura with no use / edit / publication for ``meses`` months -- once per window, an event each, never an auto-archive.
    Always logs the counts (measurable per run). Returns ``{sinalizadas, liberadas}``."""
    res = db.rpc("cs_estruturas_revisao_desuso", {"p_meses": int(meses)}).execute()
    data = getattr(res, "data", None)
    data = data[0] if isinstance(data, list) and data else data
    out = {"sinalizadas": int((data or {}).get("sinalizadas") or 0), "liberadas": int((data or {}).get("liberadas") or 0)}
    logger.info("biblioteca revisão por desuso (%d meses): %d sinalizada(s), %d liberada(s)", meses, out["sinalizadas"], out["liberadas"])
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
        dias_ret = int(dias if dias is not None else settings.biblioteca_retencao_dias)
        rascunhos = expirar_rascunhos_automaticos(db, dias=dias_ret)
        orfaos = await varrer_blobs_orfaos(db, st)
        importacoes = await varrer_blobs_importacao(db, st)
        revisao = sinalizar_revisao_por_desuso(db)
        if any(purga.values()) or any(orfaos.values()) or any(importacoes.values()) or any(revisao.values()) or any(rascunhos.values()):
            logger.info("biblioteca retenção: %s rascunhos: %s órfãos: %s importações: %s revisão: %s", purga, rascunhos, orfaos, importacoes, revisao)
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
    "IMPORTACAO_BLOB_TTL_DIAS",
    "REVISAO_DESUSO_MESES",
    "expirar_rascunhos_automaticos",
    "purgar_expirados",
    "run_retencao",
    "sinalizar_revisao_por_desuso",
    "varrer_blobs_importacao",
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
