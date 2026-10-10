"""Transcription product service: submit (the abuse shield), read, cancel, stats.

Validation order of ``submit`` is the contract's section 3, synchronous and BEFORE
anything is queued: kill switch -> size (stream cut, 413) -> magic bytes (415) ->
context ownership -> probe via the transcriber (422) -> quota reservation on the
PROBED duration (429/503). Nothing here logs transcript text or an audio path.
"""
from __future__ import annotations

import dataclasses
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.transcription import (
    DEFAULT_LIMITS,
    ProbeNotSupported,
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionError,
    TranscriptionLimits,
    TranscriptionNotConfigured,
    TranscriptionRejected,
)
from noctusai_lib.integrations.transcription.validation import check_format, check_probe, sniff_container

from app.modules.transcricoes import hooks
from app.modules.transcricoes.deps import BUCKET, KillSwitch, TranscriberFactory
from app.modules.transcricoes.errors import TranscricaoErro, mensagem_de

logger = logging.getLogger(__name__)

TABLE = "transcricoes"
RPC_RESERVAR = "reservar_transcricao"
JOB_TYPE = "transcricao"
IN_FLIGHT = ("na_fila", "processando")
COLS = (
    "id,org_id,user_id,contexto_tipo,contexto_ref,storage_path,bytes,duracao_s,formato,status,texto,"
    "erro_codigo,modelo,rtf,criado_em,iniciado_em,concluido_em,audio_apagado_em,minutos_reembolsados,"
    "hook_aplicado_em"
)
#: Expected wall time per second of audio, for the ETA shown while queued (the
#: contract's measurement gate is RTF <= 1.5).
ETA_RTF = 1.5
#: Multipart framing slack on top of the file cap (also the body-size override).
MULTIPART_OVERHEAD_BYTES = 512 * 1024
READ_CHUNK_BYTES = 1024 * 1024
#: ``max_retries`` of the queue row; the worker's RetryPolicy is the authority.
JOB_MAX_RETRIES = 2

MAX_BODY_BYTES = DEFAULT_LIMITS.max_bytes + MULTIPART_OVERHEAD_BYTES


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime] = None) -> str:
    return (dt or now()).isoformat()


# --------------------------------------------------------------------------
# reads / presentation (shared with the Cérebro brain detail)
# --------------------------------------------------------------------------


def fila_snapshot(db: Any) -> list[dict[str, Any]]:
    """Every in-flight job (global, oldest first). Bounded: the quota RPC caps the
    queue depth at 20."""
    rows = (
        db.table(TABLE).select("id,status,duracao_s,criado_em")
        .in_("status", list(IN_FLIGHT)).execute().data or []
    )
    return sorted(rows, key=lambda r: (str(r.get("criado_em") or ""), str(r.get("id"))))


def posicao_e_estimativa(snapshot: list[dict[str, Any]], transcricao_id: str) -> tuple[Optional[int], Optional[int]]:
    """1-based place of a QUEUED job (a running one counts as ahead) and a rough ETA."""
    ahead = 0.0
    for idx, r in enumerate(snapshot):
        if str(r["id"]) == str(transcricao_id):
            if r.get("status") != "na_fila":
                return None, None
            return idx + 1, int(round((ahead + float(r.get("duracao_s") or 0)) * ETA_RTF))
        ahead += float(r.get("duracao_s") or 0)
    return None, None


def transcricao_out(row: dict[str, Any], posicao: Optional[int] = None) -> dict[str, Any]:
    """The public job shape (``GET /api/transcricoes/{id}`` and ``Answer.transcricao``)."""
    erro = None
    if row.get("status") == "falhou":
        codigo = row.get("erro_codigo") or "falhou"
        erro = {"codigo": codigo, "mensagem": mensagem_de(codigo)}
    return {
        "id": row["id"],
        "status": row["status"],
        "posicao": posicao if row.get("status") == "na_fila" else None,
        "duracao_s": float(row["duracao_s"]) if row.get("duracao_s") is not None else None,
        "texto": row.get("texto") if row.get("status") == "concluida" else None,
        "erro": erro,
        "criado_em": row.get("criado_em"),
        "concluido_em": row.get("concluido_em"),
    }


def transcricoes_por_id(db: Any, org_id: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    """``{id: public job shape}`` for ``ids`` (org-scoped), queue positions included."""
    ids = [i for i in dict.fromkeys(str(i) for i in ids if i)]
    if not ids:
        return {}
    rows = (
        db.table(TABLE).select(COLS).in_("id", ids).eq("org_id", org_id).execute().data or []
    )
    snapshot = fila_snapshot(db) if any(r.get("status") == "na_fila" for r in rows) else []
    return {
        str(r["id"]): transcricao_out(r, posicao_e_estimativa(snapshot, r["id"])[0]) for r in rows
    }


def load_row(db: Any, transcricao_id: str) -> Optional[dict[str, Any]]:
    """Unscoped read (worker / sweep, service role)."""
    rows = db.table(TABLE).select(COLS).eq("id", str(transcricao_id)).execute().data or []
    return rows[0] if rows else None


# --------------------------------------------------------------------------
# state changes shared by the request path, the worker and the sweep
# --------------------------------------------------------------------------


def marcar_falha(
    db: Any, transcricao_id: str, codigo: str, *, reembolsar: bool, estados: tuple[str, ...] = IN_FLIGHT
) -> bool:
    """Move an in-flight job to ``falhou`` (refunding its minutes when the failure
    is ours). Conditional on the current state so a concurrent cancel/finish wins."""
    patch: dict[str, Any] = {"status": "falhou", "erro_codigo": codigo, "concluido_em": iso()}
    if reembolsar:
        patch["minutos_reembolsados"] = True
    res = (
        db.table(TABLE).update(patch).eq("id", str(transcricao_id)).in_("status", list(estados))
        .execute().data
    )
    return bool(res)


async def apagar_audio(db: Any, storage: StorageBackend, row: dict[str, Any]) -> bool:
    """Delete the recording and stamp ``audio_apagado_em``. A failed delete is logged
    (ids only) and left for the retention sweep."""
    if row.get("audio_apagado_em"):
        return True
    try:
        await storage.delete(bucket=BUCKET, key=row["storage_path"])
    except Exception:  # noqa: BLE001 - retried by the sweep; never raises into the job
        logger.warning("transcricoes: audio delete failed id=%s (the sweep retries)", row.get("id"), exc_info=True)
        return False
    db.table(TABLE).update({"audio_apagado_em": iso()}).eq("id", str(row["id"])).execute()
    return True


def _storage_key(org_id: str, user_id: str, transcricao_id: str, formato: str) -> str:
    """``org/user/uuid.ext`` — the client's filename is never used."""
    return f"{org_id}/{user_id}/{transcricao_id}.{formato}"


_CONTENT_TYPES = {
    "webm": "audio/webm", "ogg": "audio/ogg", "mp4": "audio/mp4", "mp3": "audio/mpeg", "wav": "audio/wav",
}


class TranscricaoService:
    def __init__(
        self,
        db: Any,
        org_id: str,
        user_id: str,
        *,
        storage: StorageBackend,
        jobs: JobRepository,
        transcriber_factory: TranscriberFactory,
        kill_switch: KillSwitch,
        limits: TranscriptionLimits = DEFAULT_LIMITS,
    ) -> None:
        self.db = db
        self.org_id = str(org_id)
        self.user_id = str(user_id)
        self.storage = storage
        self.jobs = jobs
        self._transcriber_factory = transcriber_factory
        self._kill_switch = kill_switch
        self.limits = limits

    # ── submit ──────────────────────────────────────────────────────────

    async def ler_upload(self, arquivo: Any) -> bytes:
        """Read an ``UploadFile`` in chunks, cutting the stream at the cap (413)."""
        buf = bytearray()
        while True:
            chunk = await arquivo.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > self.limits.max_bytes:
                raise TranscricaoErro("arquivo_grande")
        return bytes(buf)

    async def submit_upload(self, arquivo: Any, contexto_tipo: str, contexto_ref: str) -> dict[str, Any]:
        if not self._kill_switch():
            raise TranscricaoErro("transcricao_desativada")
        data = await self.ler_upload(arquivo)
        return await self.submit(data, contexto_tipo, contexto_ref, checar_chave=False)

    async def submit(
        self, data: bytes, contexto_tipo: str, contexto_ref: str, *, checar_chave: bool = True
    ) -> dict[str, Any]:
        if checar_chave and not self._kill_switch():
            raise TranscricaoErro("transcricao_desativada")
        # 1. size
        if len(data) > self.limits.max_bytes:
            raise TranscricaoErro("arquivo_grande")
        # 2. magic bytes
        if check_format(data, self.limits):
            raise TranscricaoErro("formato_invalido")
        container = sniff_container(data)
        # 2b. who is this recording for (ownership; unknown type)
        handler = hooks.get_contexto(contexto_tipo)
        if handler is None:
            raise TranscricaoErro("contexto_invalido")
        handler.validar(self.db, self.org_id, self.user_id, contexto_ref)
        # 3. probe (the transcriber's ffprobe: container/codec/duration)
        probe = await self._probe(data)
        codigo = check_probe(probe, self.limits)
        if codigo:
            # section 3 step 3: a probed-format failure is a 422 (not the 415 of step 2)
            raise TranscricaoErro(codigo, status=422)
        # 4. quota, charged on the PROBED duration
        transcricao_id = str(uuid.uuid4())
        path = _storage_key(self.org_id, self.user_id, transcricao_id, container)
        row = self._reservar(transcricao_id, probe.duracao_s, len(data), container, contexto_tipo, contexto_ref, path)
        # 5. store + enqueue; any failure releases the reservation
        try:
            await self.storage.put(
                bucket=BUCKET, key=path, data=data, content_type=_CONTENT_TYPES.get(container, "application/octet-stream")
            )
            await self.jobs.enqueue(
                type=JOB_TYPE, payload={"transcricao_id": transcricao_id},
                max_retries=JOB_MAX_RETRIES, dedupe_key=f"{JOB_TYPE}:{transcricao_id}",
            )
        except Exception:
            logger.error("transcricoes: store/enqueue failed id=%s; releasing the reservation", transcricao_id, exc_info=True)
            marcar_falha(self.db, transcricao_id, "transcricao_indisponivel", reembolsar=True)
            try:
                await self.storage.delete(bucket=BUCKET, key=path)
            except Exception:  # noqa: BLE001 - the sweep deletes a failed row's audio
                logger.warning("transcricoes: cleanup delete failed id=%s", transcricao_id, exc_info=True)
            raise TranscricaoErro("transcricao_indisponivel") from None
        posicao, estimativa = posicao_e_estimativa(fila_snapshot(self.db), row["id"])
        logger.info(
            "transcricao.enfileirada id=%s org=%s user=%s bytes=%s duracao_s=%s posicao=%s",
            row["id"], self.org_id, self.user_id, len(data), probe.duracao_s, posicao,
        )
        return {
            "id": row["id"], "status": "na_fila", "posicao": posicao or 1,
            "estimativa_s": estimativa or int(round(probe.duracao_s * ETA_RTF)),
            "duracao_s": float(probe.duracao_s),
        }

    async def _probe(self, data: bytes):
        try:
            return await self._transcriber_factory().probe(data)
        except TranscriptionNotConfigured as exc:
            logger.error("transcricoes: transcriber not configured: %s", exc)
            raise TranscricaoErro("transcricao_indisponivel") from None
        except TranscriptionRejected as exc:
            # The engine could not read it: a corrupt / unsupported file (422).
            codigo = exc.codigo if exc.codigo in ("formato_invalido", "duracao_excedida", "audio_vazio") else "audio_corrompido"
            raise TranscricaoErro(codigo, status=422) from None
        except TranscriberBusy as exc:
            raise TranscricaoErro("transcricao_indisponivel", retry_after_s=int(exc.retry_after_s)) from None
        except (TranscriberUnavailable, ProbeNotSupported) as exc:
            # Quota is charged on the PROBED duration only — no probe, no submit.
            logger.error("transcricoes: probe unavailable: %s", exc)
            raise TranscricaoErro("transcricao_indisponivel") from None
        except TranscriptionError as exc:
            logger.error("transcricoes: probe failed: %s", exc)
            raise TranscricaoErro("transcricao_indisponivel") from None

    def _reservar(
        self, transcricao_id: str, duracao_s: float, size: int, formato: str,
        contexto_tipo: str, contexto_ref: str, path: str,
    ) -> dict[str, Any]:
        res = self.db.rpc(RPC_RESERVAR, {
            "p_id": transcricao_id, "p_org": self.org_id, "p_user": self.user_id,
            "p_duracao_s": float(duracao_s), "p_bytes": size, "p_formato": formato,
            "p_contexto_tipo": contexto_tipo, "p_contexto_ref": contexto_ref, "p_storage_path": path,
        }).execute().data
        if isinstance(res, list):
            res = res[0] if res else None
        if not isinstance(res, dict):
            logger.error("transcricoes: reservar_transcricao returned %r", type(res).__name__)
            raise TranscricaoErro("transcricao_indisponivel")
        if not res.get("ok"):
            raise TranscricaoErro(
                str(res.get("codigo") or "transcricao_indisponivel"),
                status=res.get("http"), retry_after_s=res.get("retry_after_s"),
            )
        return res["row"]

    # ── read / cancel ───────────────────────────────────────────────────

    def _own_row(self, transcricao_id: str) -> dict[str, Any]:
        rows = (
            self.db.table(TABLE).select(COLS)
            .eq("id", str(transcricao_id)).eq("org_id", self.org_id).eq("user_id", self.user_id)
            .execute().data or []
        )
        if not rows:
            # 404, never 403: another user's job id must be indistinguishable from none.
            raise TranscricaoErro("nao_encontrada")
        return rows[0]

    def get(self, transcricao_id: str) -> dict[str, Any]:
        row = self._own_row(transcricao_id)
        posicao = None
        if row["status"] == "na_fila":
            posicao = posicao_e_estimativa(fila_snapshot(self.db), row["id"])[0]
        return transcricao_out(row, posicao)

    async def cancel(self, transcricao_id: str) -> dict[str, Any]:
        row = self._own_row(transcricao_id)
        if row["status"] == "processando":
            raise TranscricaoErro("em_processamento")
        if row["status"] != "na_fila":
            raise TranscricaoErro("nao_cancelavel")
        won = (
            self.db.table(TABLE)
            .update({"status": "cancelada", "concluido_em": iso(), "minutos_reembolsados": True})
            .eq("id", row["id"]).eq("status", "na_fila").execute().data
        )
        if not won:  # the worker claimed it between our read and the update
            raise TranscricaoErro("em_processamento")
        await apagar_audio(self.db, self.storage, row)
        return transcricao_out(self._own_row(row["id"]))

    # ── admin ───────────────────────────────────────────────────────────

    async def stats(self) -> dict[str, Any]:
        queue = await self.jobs.queue_stats(job_types=[JOB_TYPE])
        queue_out = {
            k: (v.isoformat() if isinstance(v, datetime) else list(v) if isinstance(v, tuple) else v)
            for k, v in dataclasses.asdict(queue).items()
        }
        since = iso(now() - timedelta(hours=24))
        rows = (
            self.db.table(TABLE).select("org_id,duracao_s,status,minutos_reembolsados")
            .gte("criado_em", since).execute().data or []
        )
        minutos: dict[str, float] = {}
        por_status: dict[str, int] = {}
        for r in rows:
            por_status[r["status"]] = por_status.get(r["status"], 0) + 1
            if not r.get("minutos_reembolsados"):
                minutos[str(r["org_id"])] = minutos.get(str(r["org_id"]), 0.0) + float(r["duracao_s"] or 0) / 60.0
        return {
            "queue_stats": queue_out,
            "ultimas_24h": {
                "por_status": por_status,
                "minutos_por_org": {k: round(v, 2) for k, v in sorted(minutos.items())},
                "minutos_total": round(sum(minutos.values()), 2),
            },
        }
