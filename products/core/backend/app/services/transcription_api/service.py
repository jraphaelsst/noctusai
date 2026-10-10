"""Submit / read / list / cancel / stats for the platform transcription API.

Validation order (CONTRACT §3, synchronous, before anything is queued):
streamed size cap -> magic bytes -> kill switch -> worker probe -> quota RPC
-> store audio -> enqueue. Quota is charged on the PROBED duration."""
from __future__ import annotations

import base64
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.transcription import (
    ProbeNotSupported,
    Transcriber,
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionError,
    TranscriptionLimits,
    TranscriptionRejected,
)
from noctusai_lib.integrations.transcription.validation import (
    check_format,
    check_probe,
    check_size,
    sniff_container,
)

from app.services.transcription_api import limits as L
from app.services.transcription_api.errors import (
    CODIGOS,
    CODIGOS_RPC,
    TranscricaoErro,
    mensagem_de_falha,
)
from app.services.transcription_api.repository import (
    ACTIVE,
    TranscricaoRepo,
    iso,
    parse_ts,
    utcnow,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Caller:
    """Caller identity (CONTRACT §1): ``token`` + api_tokens.id, or ``user`` + user_id."""

    kind: str
    id: str
    org_id: str

    @property
    def identity(self) -> str:
        return f"{self.kind}:{self.id}"


def caller_from_context(ctx: Any) -> Caller:
    """``AuthContext`` -> :class:`Caller`. Product (``pk_*``) callers are
    ``token`` identified by the token row id; sessions are ``user``."""
    if ctx.caller_kind == "product":
        ident = ctx.api_token_id
        kind = "token"
    else:
        ident = ctx.user_id
        kind = "user"
    if ident is None:
        raise TranscricaoErro("escopo_insuficiente")
    return Caller(kind=kind, id=str(ident), org_id=str(ctx.org_id))


class TranscricaoService:
    def __init__(
        self,
        *,
        repo: TranscricaoRepo,
        jobs: JobRepository,
        storage: StorageBackend,
        get_transcriber: Callable[[], Transcriber],
        kill_switch: L.KillSwitch,
        limits: TranscriptionLimits,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.repo = repo
        self.jobs = jobs
        self.storage = storage
        self._get_transcriber = get_transcriber
        self.kill_switch = kill_switch
        self.limits = limits
        self._clock = clock
        #: Last transcriber failure seen on any path (None = last contact fine).
        self.transcriber_error: Optional[str] = None

    # -- helpers -------------------------------------------------------

    def transcriber(self) -> Transcriber:
        try:
            return self._get_transcriber()
        except TranscriptionError:
            # Misconfiguration (e.g. local_whisper without URL/token): loud in
            # the log, never a silent fallback to another backend.
            logger.exception("transcricao.transcriber_not_configured")
            self.transcriber_error = "nao_configurado"
            raise TranscricaoErro(
                "transcricao_indisponivel", retry_after_s=L.TRANSCRIBER_RETRY_AFTER_S
            )

    @staticmethod
    def _path(caller: Caller, transcricao_id: str, container: str) -> str:
        return f"{caller.org_id}/{caller.kind}/{caller.id}/{transcricao_id}.{container}"

    # -- submit --------------------------------------------------------

    async def submit(
        self,
        caller: Caller,
        audio: bytes,
        *,
        idioma: str = "pt",
        rotulo: Optional[str] = None,
        segmentos: bool = False,
    ) -> dict:
        if idioma not in L.LANGUAGES:
            raise TranscricaoErro("formato_invalido")
        if rotulo is not None and len(rotulo) > L.ROTULO_MAX_CHARS:
            raise TranscricaoErro("formato_invalido")

        # 1. size, 2. magic bytes
        codigo = check_size(len(audio), self.limits) or check_format(audio, self.limits)
        if codigo:
            raise TranscricaoErro(codigo)
        container = sniff_container(audio)

        # 3. kill switch
        if not self.kill_switch.habilitada():
            raise TranscricaoErro(
                "transcricao_desativada", retry_after_s=L.KILL_SWITCH_RETRY_AFTER_S
            )

        # 4. worker probe (duration + codec)
        probe = await self._probe(audio)
        codigo = check_probe(probe, self.limits)
        if codigo:
            raise TranscricaoErro(codigo)
        duracao_s = float(probe.duracao_s)

        # 5. quota RPC (atomic; inserts the na_fila row)
        reserva = self.repo.reservar(
            caller_kind=caller.kind, caller_id=caller.id, org_id=caller.org_id, duracao_s=duracao_s
        )
        if not reserva.get("ok"):
            codigo = reserva.get("codigo")
            if codigo not in CODIGOS_RPC:
                logger.error("transcricao.rpc_codigo_desconhecido codigo=%s", codigo)
                raise TranscricaoErro(
                    "transcricao_indisponivel", retry_after_s=L.TRANSCRIBER_RETRY_AFTER_S
                )
            raise TranscricaoErro(codigo, retry_after_s=reserva.get("retry_after_s"))
        tid = str(reserva["id"])

        # 6. store audio, 7. enqueue — any failure here is OUR fault: fail + refund.
        path = self._path(caller, tid, container)
        try:
            await self.storage.put(
                bucket=L.BUCKET, key=path, data=audio, content_type=f"audio/{container}"
            )
            self.repo.update(
                tid,
                {
                    "storage_path": path,
                    "bytes": len(audio),
                    "formato": container,
                    "idioma": idioma,
                    "rotulo": rotulo,
                    # `segmentos` has no flag column: [] = "requested", NULL = not.
                    "segmentos": [] if segmentos else None,
                },
            )
            await self.jobs.enqueue(
                type=L.JOB_TYPE,
                payload={"transcricao_id": tid},
                max_retries=L.JOB_MAX_RETRIES,
                dedupe_key=f"{L.JOB_TYPE}:{tid}",
            )
        except Exception as exc:  # noqa: BLE001 — type only: a storage message can carry the path
            logger.error("transcricao.submit_failed id=%s err=%s", tid, type(exc).__name__)
            await self.falhar(tid, "armazenamento", reembolsar=True)
            raise TranscricaoErro(
                "transcricao_indisponivel", retry_after_s=L.TRANSCRIBER_RETRY_AFTER_S
            )

        ahead, ahead_s = self.repo.fila_a_frente(tid)
        return {
            "id": tid,
            "status": "na_fila",
            "posicao": ahead + 1,
            "estimativa_s": self._estimativa(ahead_s + duracao_s),
            "duracao_s": duracao_s,
        }

    async def _probe(self, audio: bytes):
        transcriber = self.transcriber()
        try:
            probe = await transcriber.probe(audio)
        except TranscriptionRejected as exc:
            known = exc.codigo in CODIGOS and CODIGOS[exc.codigo][0] in (415, 422)
            raise TranscricaoErro(exc.codigo if known else "audio_corrompido")
        except TranscriberBusy as exc:
            raise TranscricaoErro("transcricao_indisponivel", retry_after_s=exc.retry_after_s)
        except (TranscriberUnavailable, ProbeNotSupported):
            logger.warning("transcricao.probe_unavailable", exc_info=True)
            self.transcriber_error = "probe"
            raise TranscricaoErro(
                "transcricao_indisponivel", retry_after_s=L.TRANSCRIBER_RETRY_AFTER_S
            )
        self.transcriber_error = None
        return probe

    @staticmethod
    def _estimativa(total_duracao_s: float) -> int:
        return int(round(total_duracao_s * L.RTF_ESTIMADO + 5))

    # -- failure / cancel (shared with the worker) ----------------------

    async def apagar_audio(self, row: dict) -> bool:
        """Delete the stored audio and stamp ``audio_apagado_em``. Idempotent."""
        path = row.get("storage_path")
        if not path or row.get("audio_apagado_em"):
            return False
        await self.storage.delete(bucket=L.BUCKET, key=path)
        self.repo.update(row["id"], {"audio_apagado_em": iso(self._clock())})
        return True

    async def falhar(self, tid: str, codigo: str, *, reembolsar: bool) -> bool:
        """Terminal ``falhou`` (compare-and-set from an active status). Refund
        only when the failure is ours. Audio stays for the 72 h sweep."""
        ok = self.repo.transition(
            tid,
            from_status=ACTIVE,
            fields={"status": "falhou", "erro_codigo": codigo, "concluido_em": iso(self._clock())},
        )
        if ok and reembolsar:
            self.repo.refund(tid)
        return ok

    # -- reads ---------------------------------------------------------

    def _view(self, row: dict, *, full: bool) -> dict:
        out: dict[str, Any] = {
            "id": row["id"],
            "status": row["status"],
            "duracao_s": float(row["duracao_s"]),
            "idioma": row.get("idioma"),
            "rotulo": row.get("rotulo"),
            "modelo": row.get("modelo"),
            "rtf": float(row["rtf"]) if row.get("rtf") is not None else None,
            "criado_em": row.get("criado_em"),
            "iniciado_em": row.get("iniciado_em"),
            "concluido_em": row.get("concluido_em"),
            "expira_em": row.get("expira_em"),
        }
        if row["status"] == "na_fila":
            ahead, _ = self.repo.fila_a_frente(row["id"])
            out["posicao"] = ahead + 1
        if row["status"] == "falhou":
            codigo = row.get("erro_codigo") or "transcricao_indisponivel"
            out["erro"] = {"codigo": codigo, "mensagem": mensagem_de_falha(codigo)}
        if full and row["status"] == "concluida":
            out["texto"] = row.get("texto")
            if row.get("segmentos"):
                out["segmentos"] = row["segmentos"]
        return out

    @staticmethod
    def _valid_id(transcricao_id: str) -> str:
        try:
            return str(uuid.UUID(str(transcricao_id)))
        except ValueError:
            raise TranscricaoErro("nao_encontrada")

    def obter(self, caller: Caller, transcricao_id: str) -> dict:
        transcricao_id = self._valid_id(transcricao_id)
        row = self.repo.get_for_caller(transcricao_id, caller.kind, caller.id)
        if row is None:  # other callers' jobs are 404, never 403
            raise TranscricaoErro("nao_encontrada")
        return self._view(row, full=True)

    def listar(
        self, caller: Caller, *, status: Optional[str], limit: int, cursor: Optional[str]
    ) -> dict:
        if status is not None and status not in (*ACTIVE, "concluida", "falhou", "cancelada"):
            raise TranscricaoErro("formato_invalido")
        limit = max(1, min(int(limit), 100))
        before = None
        if cursor:
            try:
                before = parse_ts(base64.urlsafe_b64decode(cursor.encode()).decode())
            except Exception:  # noqa: BLE001 — a malformed cursor is a client error
                raise TranscricaoErro("formato_invalido")
        rows = self.repo.list_for_caller(
            caller.kind, caller.id, status=status, limit=limit + 1, before=before
        )
        page = rows[:limit]
        out: dict[str, Any] = {"items": [self._view(r, full=False) for r in page]}
        if len(rows) > limit and page:
            out["next_cursor"] = base64.urlsafe_b64encode(page[-1]["criado_em"].encode()).decode()
        return out

    # -- delete --------------------------------------------------------

    async def remover(self, caller: Caller, transcricao_id: str) -> None:
        transcricao_id = self._valid_id(transcricao_id)
        row = self.repo.get_for_caller(transcricao_id, caller.kind, caller.id)
        if row is None:
            raise TranscricaoErro("nao_encontrada")
        status = row["status"]
        if status == "processando":
            raise TranscricaoErro("em_processamento")
        if status == "na_fila":
            if self.repo.transition(
                row["id"], from_status=("na_fila",),
                fields={"status": "cancelada", "concluido_em": iso(self._clock())},
            ):
                self.repo.refund(row["id"])
                await self.apagar_audio(row)
                return
            # Lost the race: the worker claimed it between our read and write.
            raise TranscricaoErro("em_processamento")
        # concluida / falhou / cancelada: purge text now (row stays for quota history).
        self.repo.update(row["id"], {"texto": None, "segmentos": None})
        await self.apagar_audio(row)

    # -- admin ---------------------------------------------------------

    def stats(self, *, worker_saudavel: bool) -> dict:
        s = self.repo.estatisticas(since=self._clock() - timedelta(hours=24))
        return {
            "fila": s["fila"],
            "processando": s["processando"],
            "minutos_hoje_global": round(s["minutos_global"], 2),
            "minutos_hoje_por_org": [
                {"org_id": org, "minutos": round(m, 2)}
                for org, m in sorted(s["minutos_por_org"].items())
            ],
            "worker_saudavel": bool(worker_saudavel and self.transcriber_error is None),
            "habilitada": self.kill_switch.habilitada(),
        }
