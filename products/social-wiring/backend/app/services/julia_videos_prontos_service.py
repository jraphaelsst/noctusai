"""Julia "Vídeos Prontos" -- the editor's WhatsApp group as an extra entry point to the EXISTING YouTube upload.

The editor posts, in the org's "Vídeos Prontos" group, a property code (`ONE10898`, `CA2411`, optionally
"(EXCLUSIVIDADE)") and the Drive folder with the finished videos -- code first, link first, or both in one message,
usually seconds apart, one submission at a time. This module pairs them and hands the folder to the youtube module:

  * `extrair` -- the PURE parser (the seed code scanner `PRODUCT_CODE_SCAN_PATTERN` + the one Drive-link scanner
    `gdrive_service.DRIVE_URL_SCAN_PATTERN`; a code is never read out of a URL).
  * pairing (`receber`) -- one OPEN `aguardando` slot per (org, chat, sender): an empty field is filled; a different
    code / folder than the open slot's closes it (scheduled now) and opens a new one; a message id already in the slot
    is a no-op. Every relevant message bumps `versao` and pushes `due_at` (the debounce,
    `julia_youtube_upload_wait_seconds`) and enqueues `julia_videos_prontos.processar` with dedupe `vp:{id}:v{versao}`:
    only the job of the CURRENT version runs.
  * processing (`processar`) -- incomplete -> `incompleto`; a (code, folder) pair already uploading / uploaded ->
    refused; else `UploadService.queue_drive_folder_upload` (an empty folder -> `no_videos_found`), every child
    `run_upload_job` in turn, outcome aggregated from `upload_jobs` -> `concluido` / `parcial` / `falhou`. The
    orientation is the worker's `target_format` (never re-classified here). The FIRST published standard (16:9) video
    fills the property's YouTube field (S1 contract `imovel_video_youtube_service`), Shorts never do.
  * retry (`retry`) -- ONE automatic retry `julia_youtube_retry_delay_seconds` after a `parcial` / `falhou`: only the
    FAILED children are retried (`retry_failed_job` + `run_upload_job`), published ones are never re-uploaded. A manual
    retry (`POST /api/julia/videos-prontos/{id}/retry`) takes the same path. No second automatic retry.
  * outcomes -- the owner gets the scripted notification (`notification_kinds` `video_pronto_*`) for every outcome; the
    group gets ONE short pt-BR message only on a problem (never on success), through the outbound gate (`interno`).
    Every transition is a transition-log event (`julia_video_pronto_events`, migration 372) and a `julia_eventos` row.

Every collaborator is a constructor seam (Fake in tests): the repository, the job queue, the upload service factory,
the metadata resolver, the S1 property-field service, the owner notifier, the group sender and the event emitter.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional, Protocol
from uuid import UUID

from noctusai_lib.domain.real_estate import PRODUCT_CODE_SCAN_PATTERN

from app.services import gdrive_service

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
T_CONFIG = "julia_videos_prontos_config"
T_SUBMISSOES = "julia_videos_prontos_submissoes"
T_UPLOAD_JOBS = "upload_jobs"

JOB_PROCESSAR = "julia_videos_prontos.processar"
JOB_RETRY = "julia_videos_prontos.retry"
#: a slot closed early (a different property arrived) is claimed at once and its upload runs as this job
JOB_EXECUTAR = "julia_videos_prontos.executar"
JOB_TYPES: tuple[str, ...] = (JOB_PROCESSAR, JOB_RETRY, JOB_EXECUTAR)

AGUARDANDO, INCOMPLETO, PROCESSANDO = "aguardando", "incompleto", "processando"
CONCLUIDO, PARCIAL, FALHOU, SEM_VIDEOS = "concluido", "parcial", "falhou", "no_videos_found"
STATUS: frozenset[str] = frozenset({AGUARDANDO, INCOMPLETO, PROCESSANDO, CONCLUIDO, PARCIAL, FALHOU, SEM_VIDEOS})
RETENTAVEIS: frozenset[str] = frozenset({PARCIAL, FALHOU})

#: Closed failure reason codes (`motivo`); the human text is `ERROS[motivo]`.
MOTIVO_FALTOU_CODIGO = "faltou_codigo"
MOTIVO_FALTOU_LINK = "faltou_link"
MOTIVO_DUPLICADO = "duplicado"
MOTIVO_PASTA_VAZIA = "pasta_vazia"
MOTIVO_PASTA_INACESSIVEL = "pasta_inacessivel"
MOTIVO_IMOVEL_NAO_ENCONTRADO = "imovel_nao_encontrado"
MOTIVO_CATALOGO_INDISPONIVEL = "catalogo_indisponivel"
MOTIVO_YOUTUBE_INDISPONIVEL = "youtube_indisponivel"
MOTIVO_UPLOAD_FALHOU = "upload_falhou"
MOTIVO_ERRO_INTERNO = "erro_interno"
ERROS: dict[str, str] = {
    MOTIVO_FALTOU_CODIGO: "faltou o código do imóvel",
    MOTIVO_FALTOU_LINK: "faltou o link da pasta do Drive",
    MOTIVO_DUPLICADO: "essa pasta já foi enviada ao YouTube para este imóvel",
    MOTIVO_PASTA_VAZIA: "a pasta do Drive não tem vídeos (ou não está compartilhada com qualquer pessoa com o link)",
    MOTIVO_PASTA_INACESSIVEL: "não foi possível abrir a pasta do Drive (confira o compartilhamento)",
    MOTIVO_IMOVEL_NAO_ENCONTRADO: "o código não existe no cadastro de imóveis",
    MOTIVO_CATALOGO_INDISPONIVEL: "o cadastro de imóveis não respondeu",
    MOTIVO_YOUTUBE_INDISPONIVEL: "o YouTube da organização não está conectado/configurado",
    MOTIVO_UPLOAD_FALHOU: "o envio ao YouTube falhou",
    MOTIVO_ERRO_INTERNO: "erro interno ao processar",
}

#: `upload_jobs.status` values that mean the video is on YouTube.
PUBLICADOS: frozenset[str] = frozenset({"published", "notified"})
#: The property-field rule: only a standard (16:9) upload fills it -- Shorts never do.
FORMATO_PADRAO = "youtube"

ORIGEM_JULIA = "julia"
MOTIVO_CAMPO_IMOVEL = "Vídeo publicado via grupo Vídeos Prontos ONE (Julia)"

_EXCLUSIVIDADE_RE = re.compile(r"\bexclusividade\b", re.IGNORECASE)


# ─── parser (pure) ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Extracao:
    """What one message brings: the first property code, the first Drive FOLDER link, the exclusivity mark."""

    codigo: Optional[str] = None
    drive_folder_url: Optional[str] = None
    drive_folder_id: Optional[str] = None
    exclusividade: bool = False

    @property
    def relevante(self) -> bool:
        """Only a code or a folder link touches a submission (a chat line, an emoji, a file link: ignored)."""
        return bool(self.codigo or self.drive_folder_id)


def extrair(texto: str) -> Extracao:
    """Parse one group message. The Drive links are cut out BEFORE the code scan -- a folder id like
    `1aB-XYZ12345-...` would otherwise read as the code `XYZ12345`. Only a FOLDER link counts (`parse_folder_id`)."""
    texto = texto or ""
    url = folder_id = None
    for m in gdrive_service.DRIVE_URL_SCAN_PATTERN.finditer(texto):
        candidato = m.group(0).rstrip(").,;!>]")
        try:
            folder_id = gdrive_service.parse_folder_id(candidato)
        except gdrive_service.InvalidDriveURL:
            continue
        url = candidato
        break
    sem_links = gdrive_service.DRIVE_URL_SCAN_PATTERN.sub(" ", texto)
    m_codigo = PRODUCT_CODE_SCAN_PATTERN.search(sem_links)
    return Extracao(
        codigo=m_codigo.group(0).upper() if m_codigo else None,
        drive_folder_url=url,
        drive_folder_id=folder_id,
        exclusividade=bool(_EXCLUSIVIDADE_RE.search(sem_links)),
    )


# ─── ports ──────────────────────────────────────────────────────────────────
class SubmissoesRepo(Protocol):
    def config_ativa(self, connection_id: Any, chat_id: str) -> Optional[dict]: ...
    def config_da_org(self, org_id: Any) -> Optional[dict]: ...
    def aberta(self, org_id: Any, chat_id: str, remetente: str) -> Optional[dict]: ...
    def mensagem_ja_vista(self, org_id: Any, chat_id: str, mensagem_id: str) -> bool: ...
    def obter(self, submissao_id: Any) -> Optional[dict]: ...
    def criar(self, org_id: Any, row: dict) -> Optional[dict]: ...
    def atualizar_aberta(self, submissao_id: Any, *, versao_esperada: int, campos: dict) -> bool: ...
    def atualizar(self, submissao_id: Any, campos: dict) -> None: ...
    def transicionar(self, org_id: Any, submissao_id: Any, *, de: str, para: str, evento: str, dados: dict,
                     ator_id: Optional[str] = None) -> bool: ...
    def par_em_uso(self, org_id: Any, codigo: str, drive_folder_id: str, *, exceto: Any) -> Optional[dict]: ...
    def jobs_do_lote(self, batch_id: Any) -> list[dict]: ...
    def listar(self, org_id: Any, limite: int) -> list[dict]: ...


class UploadPort(Protocol):
    """The slice of `UploadService` this intake drives (never re-implemented)."""

    def queue_drive_folder_upload(self, *, org_id: UUID, created_by: Optional[UUID], metadata: Any,
                                  drive_folder_url: str) -> Any: ...
    def run_upload_job(self, *, job_id: UUID) -> None: ...
    def retry_failed_job(self, *, job_id: UUID, org_id: UUID) -> dict: ...


class ImovelVideoPort(Protocol):
    """S1's contract (`app.services.imovel_video_youtube_service`): set the property's YouTube video."""

    def definir(self, org_id: Any, codigo: str, *, youtube_video_id: str, origem: str, motivo: str,
                upload_job_id: Any) -> Any: ...


class JobsPort(Protocol):
    async def enqueue(self, *, type: str, payload: dict, max_retries: int = 3, scheduled_for: Optional[datetime] = None,
                      dedupe_key: Optional[str] = None) -> Any: ...


Notificar = Callable[[Any, str, str, str], Awaitable[Any]]  # (org_id, kind, assunto, texto)
EnviarGrupo = Callable[[Any, Any, str, str], Awaitable[Optional[str]]]  # (org_id, connection_id, chat_id, texto) -> erro
Emitir = Callable[[Any, str, dict], Any]  # (org_id, tipo, payload)
ResolverMetadados = Callable[[Any, str, str], Any]  # (org_id, codigo, privacy_status) -> UploadMetadata


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _url_video(video_id: str, target_format: Optional[str]) -> str:
    return f"https://youtube.com/shorts/{video_id}" if target_format == "shorts" else f"https://youtu.be/{video_id}"


def _causas(exc: BaseException) -> Iterable[BaseException]:
    seen: set[int] = set()
    atual: Optional[BaseException] = exc
    while atual is not None and id(atual) not in seen:
        seen.add(id(atual))
        yield atual
        atual = atual.__cause__ or atual.__context__


@dataclass
class Resultado:
    """The aggregate of one batch, from `upload_jobs` (the row is the truth, never the call stack)."""

    publicados: list[dict] = field(default_factory=list)
    falhos: list[dict] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.publicados and not self.falhos:
            return CONCLUIDO
        return PARCIAL if self.publicados else FALHOU


def agregar(jobs: list[dict]) -> Resultado:
    r = Resultado()
    for job in jobs:
        (r.publicados if job.get("status") in PUBLICADOS and job.get("youtube_video_id") else r.falhos).append(job)
    return r


# ─── the service ────────────────────────────────────────────────────────────
class JuliaVideosProntosService:
    def __init__(
        self,
        *,
        repo: SubmissoesRepo,
        jobs: JobsPort,
        upload_factory: Callable[[], UploadPort],
        resolver_metadados: ResolverMetadados,
        imovel_video_factory: Callable[[], ImovelVideoPort],
        notificar: Notificar,
        enviar_grupo: EnviarGrupo,
        emitir: Emitir,
        wait_seconds: float,
        retry_delay_seconds: float,
        agora: Callable[[], datetime] = _agora,
    ) -> None:
        self.repo = repo
        self.jobs = jobs
        self._upload_factory = upload_factory
        self._resolver = resolver_metadados
        self._imovel_video_factory = imovel_video_factory
        self._notificar = notificar
        self._enviar_grupo = enviar_grupo
        self._emitir = emitir
        self.wait_seconds = float(wait_seconds)
        self.retry_delay_seconds = float(retry_delay_seconds)
        self._agora = agora

    # ── pairing ────────────────────────────────────────────────────────────
    async def receber(self, *, org_id: Any, connection_id: Any, chat_id: str, remetente: str,
                      mensagem_id: Optional[str], texto: str) -> str:
        """One group message. Returns the outcome label: ignorada | duplicada | aberta | atualizada | conflito."""
        ext = extrair(texto)
        if not ext.relevante:
            return "ignorada"
        # a redelivered message is a no-op whichever slot it built (an open one, or one already closed / processed --
        # else a late redelivery of the PREVIOUS property's code would close the slot now open)
        if mensagem_id and self.repo.mensagem_ja_vista(org_id, chat_id, mensagem_id):
            return "duplicada"
        for _ in range(4):  # optimistic concurrency: a lost race re-reads the slot
            aberta = self.repo.aberta(org_id, chat_id, remetente)
            if aberta is not None and mensagem_id and mensagem_id in (aberta.get("ids_mensagens") or []):
                return "duplicada"
            if aberta is None:
                criada = self._abrir(org_id, connection_id, chat_id, remetente, mensagem_id, ext)
                if criada is None:
                    continue
                await self._agendar(criada)
                self._evento(org_id, "video_pronto_recebido", criada)
                return "aberta"
            if self._conflita(aberta, ext):
                await self._fechar(aberta)
                continue  # the slot left `aguardando`: the next pass opens the new one
            campos = self._mesclar(aberta, ext, mensagem_id)
            if self.repo.atualizar_aberta(aberta["id"], versao_esperada=int(aberta["versao"]), campos=campos):
                await self._agendar({**aberta, **campos})
                self._evento(org_id, "video_pronto_recebido", {**aberta, **campos})
                return "atualizada"
        logger.error("videos prontos: slot contention never settled org=%s chat=%s", org_id, chat_id)
        self._emitir(org_id, "acao_falhou", {"acao": "video_pronto_receber", "motivo": "concorrencia"})
        return "conflito"

    @staticmethod
    def _conflita(aberta: dict, ext: Extracao) -> bool:
        if ext.codigo and aberta.get("codigo") and ext.codigo != aberta["codigo"]:
            return True
        return bool(ext.drive_folder_id and aberta.get("drive_folder_id") and ext.drive_folder_id != aberta["drive_folder_id"])

    def _mesclar(self, aberta: dict, ext: Extracao, mensagem_id: Optional[str]) -> dict:
        ids = list(aberta.get("ids_mensagens") or [])
        if mensagem_id:
            ids.append(mensagem_id)
        campos: dict[str, Any] = {
            "versao": int(aberta["versao"]) + 1,
            "due_at": _iso(self._agora() + timedelta(seconds=self.wait_seconds)),
            "ids_mensagens": ids,
            "exclusividade": bool(aberta.get("exclusividade")) or ext.exclusividade,
        }
        if not aberta.get("codigo") and ext.codigo:
            campos["codigo"] = ext.codigo
        if not aberta.get("drive_folder_id") and ext.drive_folder_id:
            campos["drive_folder_url"] = ext.drive_folder_url
            campos["drive_folder_id"] = ext.drive_folder_id
        return campos

    def _abrir(self, org_id: Any, connection_id: Any, chat_id: str, remetente: str, mensagem_id: Optional[str],
               ext: Extracao) -> Optional[dict]:
        row = {
            "connection_id": str(connection_id) if connection_id else None,
            "chat_id": chat_id,
            "remetente": remetente,
            "codigo": ext.codigo,
            "drive_folder_url": ext.drive_folder_url,
            "drive_folder_id": ext.drive_folder_id,
            "exclusividade": ext.exclusividade,
            "status": AGUARDANDO,
            "versao": 1,
            "due_at": _iso(self._agora() + timedelta(seconds=self.wait_seconds)),
            "ids_mensagens": [mensagem_id] if mensagem_id else [],
        }
        return self.repo.criar(org_id, row)

    async def _fechar(self, aberta: dict) -> None:
        """Close the open slot NOW (a different property / folder arrived from the same sender): it is claimed here
        (incomplete -> `incompleto`, duplicate -> refused, else `processando`) and a claimed upload runs as a job --
        never inline on the webhook path. Its pending debounce jobs then find it no longer waiting (no-op)."""
        claimed = await self._reivindicar(aberta)
        if isinstance(claimed, dict):
            await self.jobs.enqueue(type=JOB_EXECUTAR, payload={"submissao_id": str(claimed["id"])},
                                    scheduled_for=self._agora(), dedupe_key=f"vp:{claimed['id']}:x")

    async def _agendar(self, row: dict) -> None:
        versao = int(row["versao"])
        await self.jobs.enqueue(
            type=JOB_PROCESSAR, payload={"submissao_id": str(row["id"]), "versao": versao},
            scheduled_for=datetime.fromisoformat(str(row["due_at"])),
            dedupe_key=f"vp:{row['id']}:v{versao}",
        )

    # ── processing ─────────────────────────────────────────────────────────
    async def processar(self, submissao_id: Any, versao: int) -> str:
        """The debounced job. Only the CURRENT version of a still-waiting slot runs; anything else is a no-op."""
        row = self.repo.obter(submissao_id)
        if row is None or row.get("status") != AGUARDANDO or int(row.get("versao") or 0) != int(versao):
            return "obsoleto"
        claimed = await self._reivindicar(row)
        if not isinstance(claimed, dict):
            return claimed
        return await self._executar(claimed, tentativa=0)

    async def executar(self, submissao_id: Any) -> str:
        """`JOB_EXECUTAR`: the upload of a slot already claimed by `_fechar`. Runs once: a batch already queued is
        never fanned out again."""
        row = self.repo.obter(submissao_id)
        if row is None or row.get("status") != PROCESSANDO or row.get("batch_id") or int(row.get("tentativas_retry") or 0):
            return "obsoleto"
        return await self._executar(row, tentativa=0)

    async def _reivindicar(self, row: dict) -> "dict | str":
        """Leave `aguardando`: incomplete -> `incompleto`, an already-uploaded pair -> refused, else `processando`.
        Returns the fresh claimed row, or the outcome label."""
        org_id = row["org_id"]
        if not (row.get("codigo") and row.get("drive_folder_id")):
            motivo = MOTIVO_FALTOU_LINK if row.get("codigo") else MOTIVO_FALTOU_CODIGO
            if not self.repo.transicionar(org_id, row["id"], de=AGUARDANDO, para=INCOMPLETO, evento="incompleto",
                                          dados={"motivo": motivo}):
                return "obsoleto"
            return await self._encerrar({**row, "status": INCOMPLETO}, INCOMPLETO, motivo=motivo)
        if self.repo.par_em_uso(org_id, row["codigo"], row["drive_folder_id"], exceto=row["id"]) is not None:
            return await self._recusar_duplicado(row)
        try:
            claimed = self.repo.transicionar(org_id, row["id"], de=AGUARDANDO, para=PROCESSANDO, evento="upload_iniciado",
                                             dados={"codigo": row["codigo"]})
        except Exception:
            # the duplicate-pair UNIQUE index is the race backstop: a pair claimed in between refuses this claim
            if self.repo.par_em_uso(org_id, row["codigo"], row["drive_folder_id"], exceto=row["id"]) is not None:
                return await self._recusar_duplicado(row)
            raise
        if not claimed:
            return "obsoleto"
        atual = self.repo.obter(row["id"]) or {**row, "status": PROCESSANDO}
        self._evento(org_id, "video_pronto_upload_iniciado", atual, tentativa=0)
        return atual

    async def _recusar_duplicado(self, row: dict) -> str:
        if not self.repo.transicionar(row["org_id"], row["id"], de=AGUARDANDO, para=FALHOU, evento="duplicado_recusado",
                                      dados={"codigo": row.get("codigo")}):
            return "obsoleto"
        return await self._encerrar({**row, "status": FALHOU}, FALHOU, motivo=MOTIVO_DUPLICADO)

    async def _executar(self, row: dict, *, tentativa: int) -> str:
        """Fan the folder out (or retry its failed children) and close the submission. Never leaves it `processando`."""
        try:
            if tentativa and row.get("batch_id"):
                return await self._retentar_filhos(row, tentativa=tentativa)
            return await self._enviar_pasta(row, tentativa=tentativa)
        except Exception as exc:
            logger.exception("videos prontos: processing crashed submissao=%s", row.get("id"))
            return await self._finalizar(row, FALHOU, motivo=MOTIVO_ERRO_INTERNO, tentativa=tentativa,
                                         detalhe=type(exc).__name__)

    async def _enviar_pasta(self, row: dict, *, tentativa: int) -> str:
        from app.modules.youtube.services.upload import UploadServiceError
        from app.modules.youtube.services.upload_metadata import PropertyNotFound, UploadMetadataError

        org_id = row["org_id"]
        config = self.repo.config_da_org(org_id) or {}
        try:
            metadata = await asyncio.to_thread(self._resolver, org_id, row["codigo"], config.get("privacy_status") or "private")
        except PropertyNotFound:
            return await self._finalizar(row, FALHOU, motivo=MOTIVO_IMOVEL_NAO_ENCONTRADO, tentativa=tentativa)
        except UploadMetadataError as exc:
            logger.error("videos prontos: metadata lookup failed submissao=%s (%s)", row["id"], exc)
            return await self._finalizar(row, FALHOU, motivo=MOTIVO_CATALOGO_INDISPONIVEL, tentativa=tentativa)
        try:
            upload = self._upload_factory()
        except Exception as exc:
            logger.error("videos prontos: upload service unavailable org=%s (%s)", org_id, type(exc).__name__)
            return await self._finalizar(row, FALHOU, motivo=MOTIVO_YOUTUBE_INDISPONIVEL, tentativa=tentativa)
        try:
            lote = await asyncio.to_thread(
                upload.queue_drive_folder_upload, org_id=UUID(str(org_id)), created_by=None, metadata=metadata,
                drive_folder_url=row["drive_folder_url"],
            )
        except UploadServiceError as exc:
            if any(isinstance(c, gdrive_service.DriveFolderEmpty) for c in _causas(exc)):
                return await self._finalizar(row, SEM_VIDEOS, motivo=MOTIVO_PASTA_VAZIA, tentativa=tentativa)
            logger.warning("videos prontos: Drive folder fan-out failed submissao=%s (%s)", row["id"], exc)
            return await self._finalizar(row, FALHOU, motivo=MOTIVO_PASTA_INACESSIVEL, tentativa=tentativa)
        self.repo.atualizar(row["id"], {"batch_id": str(lote.batch_id)})
        row = {**row, "batch_id": str(lote.batch_id)}
        for filho in lote.children:  # one at a time: the upload queue's own budget is shared with every entry point
            await asyncio.to_thread(upload.run_upload_job, job_id=filho.job_id)
        return await self._concluir(row, tentativa=tentativa)

    async def _retentar_filhos(self, row: dict, *, tentativa: int) -> str:
        try:
            upload = self._upload_factory()
        except Exception as exc:
            logger.error("videos prontos: upload service unavailable org=%s (%s)", row["org_id"], type(exc).__name__)
            return await self._finalizar(row, FALHOU, motivo=MOTIVO_YOUTUBE_INDISPONIVEL, tentativa=tentativa)
        org = UUID(str(row["org_id"]))
        for job in self.repo.jobs_do_lote(row["batch_id"]):
            if job.get("status") != "failed":
                continue  # a published child is NEVER uploaded again
            job_id = UUID(str(job["id"]))
            await asyncio.to_thread(upload.retry_failed_job, job_id=job_id, org_id=org)
            await asyncio.to_thread(upload.run_upload_job, job_id=job_id)
        return await self._concluir(row, tentativa=tentativa)

    async def _concluir(self, row: dict, *, tentativa: int) -> str:
        resultado = agregar(self.repo.jobs_do_lote(row["batch_id"]))
        motivo = None if resultado.status == CONCLUIDO else MOTIVO_UPLOAD_FALHOU
        await self._definir_campo_imovel(row, resultado)
        return await self._finalizar(row, resultado.status, motivo=motivo, tentativa=tentativa, resultado=resultado)

    async def _definir_campo_imovel(self, row: dict, resultado: Resultado) -> None:
        """S1: the FIRST published standard video becomes the property's YouTube video, once. Shorts-only: untouched."""
        if row.get("video_imovel_youtube_id"):
            return
        padrao = next((j for j in resultado.publicados if j.get("target_format") == FORMATO_PADRAO), None)
        if padrao is None:
            return
        try:
            servico = self._imovel_video_factory()
            res = await asyncio.to_thread(
                servico.definir, row["org_id"], row["codigo"], youtube_video_id=padrao["youtube_video_id"],
                origem=ORIGEM_JULIA, motivo=MOTIVO_CAMPO_IMOVEL, upload_job_id=padrao["id"],
            )
            if inspect.isawaitable(res):
                await res
        except Exception as exc:  # the upload is final; a field write that failed is loud, never silent
            logger.error("videos prontos: property YouTube field NOT set submissao=%s codigo=%s (%s)",
                         row["id"], row.get("codigo"), type(exc).__name__)
            self._emitir(row["org_id"], "acao_falhou", {"acao": "video_pronto_campo_imovel", "submissao_id": str(row["id"]),
                                                        "codigo": row.get("codigo")})
            return
        self.repo.atualizar(row["id"], {"video_imovel_youtube_id": padrao["youtube_video_id"]})
        row["video_imovel_youtube_id"] = padrao["youtube_video_id"]

    async def _finalizar(self, row: dict, para: str, *, motivo: Optional[str], tentativa: int,
                         resultado: Optional[Resultado] = None, detalhe: Optional[str] = None) -> str:
        if not self.repo.transicionar(row["org_id"], row["id"], de=PROCESSANDO, para=para, evento=para,
                                      dados={"motivo": motivo, "tentativa": tentativa}):
            logger.error("videos prontos: could not close submissao=%s as %s (state moved)", row["id"], para)
            return "obsoleto"
        return await self._encerrar({**row, "status": para}, para, motivo=motivo, tentativa=tentativa,
                                    resultado=resultado, detalhe=detalhe)

    async def _encerrar(self, row: dict, para: str, *, motivo: Optional[str], tentativa: int = 0,
                        resultado: Optional[Resultado] = None, detalhe: Optional[str] = None) -> str:
        """After the transition: record the reason, emit, notify the owner, maybe the group, maybe arm the retry."""
        erro = ERROS.get(motivo) if motivo else None
        if detalhe and erro:
            erro = f"{erro} ({detalhe})"
        self.repo.atualizar(row["id"], {"motivo": motivo, "erro": erro})
        vai_retentar = para in RETENTAVEIS and motivo != MOTIVO_DUPLICADO and int(row.get("tentativas_retry") or 0) == 0
        tipo = {CONCLUIDO: "video_pronto_concluido", PARCIAL: "video_pronto_parcial", FALHOU: "video_pronto_falhou",
                SEM_VIDEOS: "video_pronto_sem_videos", INCOMPLETO: "video_pronto_incompleto"}[para]
        self._evento(row["org_id"], tipo, row, motivo=motivo, tentativa=tentativa,
                     publicados=len(resultado.publicados) if resultado else 0,
                     falhas=len(resultado.falhos) if resultado else 0)
        await self._avisar_dono(row, para, motivo=motivo, erro=erro, resultado=resultado, tentativa=tentativa,
                                vai_retentar=vai_retentar)
        texto_grupo = self._texto_grupo(row, para, motivo=motivo, resultado=resultado, vai_retentar=vai_retentar)
        if texto_grupo:
            await self._postar_grupo(row, texto_grupo)
        if vai_retentar:
            await self.agendar_retry(row, tentativa=1, atraso_s=self.retry_delay_seconds)
        return para

    # ── retry ──────────────────────────────────────────────────────────────
    async def agendar_retry(self, row: dict, *, tentativa: int, atraso_s: float, ator_id: Optional[str] = None) -> Any:
        return await self.jobs.enqueue(
            type=JOB_RETRY,
            payload={"submissao_id": str(row["id"]), "tentativa": int(tentativa), "ator_id": ator_id},
            scheduled_for=self._agora() + timedelta(seconds=atraso_s),
            dedupe_key=f"vp:{row['id']}:r{int(tentativa)}",
        )

    async def retry(self, submissao_id: Any, tentativa: int, ator_id: Optional[str] = None) -> str:
        row = self.repo.obter(submissao_id)
        if (row is None or row.get("status") not in RETENTAVEIS or row.get("motivo") == MOTIVO_DUPLICADO
                or int(row.get("tentativas_retry") or 0) >= int(tentativa)):
            return "obsoleto"
        if not self.repo.transicionar(row["org_id"], row["id"], de=row["status"], para=PROCESSANDO, evento="retry_iniciado",
                                      dados={"tentativa": int(tentativa)}, ator_id=ator_id):
            return "obsoleto"
        self.repo.atualizar(row["id"], {"tentativas_retry": int(tentativa), "motivo": None, "erro": None})
        atual = {**(self.repo.obter(row["id"]) or row), "status": PROCESSANDO, "tentativas_retry": int(tentativa)}
        self._evento(atual["org_id"], "video_pronto_upload_iniciado", atual, tentativa=int(tentativa))
        return await self._executar(atual, tentativa=int(tentativa))

    async def solicitar_retry(self, org_id: Any, submissao_id: Any, *, ator_id: Optional[str]) -> dict:
        """The manual retry (an org member clicks). Refuses what cannot be retried; else queues it to run now."""
        row = self.repo.obter(submissao_id)
        if row is None or str(row.get("org_id")) != str(org_id):
            raise SubmissaoNaoEncontrada(submissao_id)
        if row.get("status") not in RETENTAVEIS:
            raise RetryRecusado("status_nao_retentavel", row.get("status"))
        if row.get("motivo") == MOTIVO_DUPLICADO:
            raise RetryRecusado("duplicado", row.get("status"))
        tentativa = int(row.get("tentativas_retry") or 0) + 1
        await self.agendar_retry(row, tentativa=tentativa, atraso_s=0, ator_id=ator_id)
        return {"submissao_id": str(row["id"]), "tentativa": tentativa, "agendado": True}

    # ── outcomes ───────────────────────────────────────────────────────────
    def _evento(self, org_id: Any, tipo: str, row: dict, **extra: Any) -> None:
        payload = {"submissao_id": str(row.get("id")), "codigo": row.get("codigo"), "batch_id": row.get("batch_id"),
                   **{k: v for k, v in extra.items() if v is not None}}
        self._emitir(org_id, tipo, payload)

    async def _avisar_dono(self, row: dict, para: str, *, motivo: Optional[str], erro: Optional[str],
                           resultado: Optional[Resultado], tentativa: int, vai_retentar: bool) -> None:
        codigo = row.get("codigo") or "(sem código)"
        apos = " (após nova tentativa)" if tentativa else ""
        links = [f"• {_url_video(j['youtube_video_id'], j.get('target_format'))}"
                 f" ({'Shorts' if j.get('target_format') == 'shorts' else 'vídeo'})"
                 for j in (resultado.publicados if resultado else [])]
        if vai_retentar:
            proximo = f"Vou tentar de novo sozinha em {int(self.retry_delay_seconds // 60) or 1} min."
        else:
            # NOC-REMEDIATE[videos-prontos-tela]: no dashboard page yet; the manual retry is the org API -- 2026-11-27
            proximo = f"Para tentar de novo os que falharam: POST /api/julia/videos-prontos/{row.get('id')}/retry."
        if para == CONCLUIDO:
            kind, assunto = "video_pronto_concluido", f"Vídeos do {codigo} publicados no YouTube"
            linhas = [f"✅ Vídeos do imóvel {codigo} publicados no YouTube{apos}:", *links]
        elif para == PARCIAL:
            n = len(resultado.publicados) + len(resultado.falhos) if resultado else 0
            kind, assunto = "video_pronto_parcial", f"Vídeos do {codigo}: parte falhou"
            linhas = [f"⚠️ Imóvel {codigo}: {len(resultado.publicados) if resultado else 0} de {n} vídeos publicados{apos}; "
                      f"{len(resultado.falhos) if resultado else 0} falharam.", *links, proximo]
        elif para == FALHOU:
            kind, assunto = "video_pronto_falhou", f"Vídeos do {codigo}: envio falhou"
            linhas = [f"❌ Imóvel {codigo}: nenhum vídeo foi publicado{apos}. Motivo: {erro or ERROS[MOTIVO_UPLOAD_FALHOU]}."]
            if motivo != MOTIVO_DUPLICADO:
                linhas.append(proximo)
        elif para == SEM_VIDEOS:
            kind, assunto = "video_pronto_sem_videos", f"Vídeos do {codigo}: pasta sem vídeos"
            linhas = [f"📂 Imóvel {codigo}: {ERROS[MOTIVO_PASTA_VAZIA]}. Nada foi enviado ao YouTube.",
                      f"Pasta: {row.get('drive_folder_url')}"]
        else:
            kind, assunto = "video_pronto_incompleto", "Vídeos Prontos: faltou código ou link"
            veio = f"só o código {row['codigo']}" if row.get("codigo") else "só o link da pasta do Drive"
            linhas = [f"✋ Uma postagem no grupo Vídeos Prontos trouxe {veio}; nada foi enviado ao YouTube."]
        try:
            await self._notificar(row["org_id"], kind, assunto, "\n".join(linhas))
        except Exception as exc:  # the outcome is recorded; an owner notice that did not go is loud
            logger.error("videos prontos: owner notice %s NOT sent submissao=%s (%s)", kind, row.get("id"), type(exc).__name__)
            self._emitir(row["org_id"], "acao_falhou", {"acao": "video_pronto_aviso_dono", "kind": kind,
                                                        "submissao_id": str(row.get("id"))})

    @staticmethod
    def _texto_grupo(row: dict, para: str, *, motivo: Optional[str], resultado: Optional[Resultado],
                     vai_retentar: bool) -> Optional[str]:
        """The ONE short group message -- only on a problem, never on success."""
        codigo = row.get("codigo")
        if para == INCOMPLETO:
            if motivo == MOTIVO_FALTOU_LINK:
                return f"Recebi o código {codigo}, mas faltou o link da pasta do Drive. Pode mandar o código e o link de novo?"
            return "Recebi o link da pasta, mas faltou o código do imóvel (ex.: ONE10898). Pode mandar o código e o link de novo?"
        if para == SEM_VIDEOS:
            return (f"Não encontrei vídeos na pasta do {codigo}. Confira se os vídeos estão nela e se a pasta está "
                    "compartilhada com qualquer pessoa com o link.")
        if motivo == MOTIVO_PASTA_INACESSIVEL:
            return f"Não consegui abrir a pasta do {codigo}. Confira se ela está compartilhada com qualquer pessoa com o link."
        if motivo == MOTIVO_DUPLICADO:
            return f"Os vídeos do {codigo} dessa pasta já foram enviados ao YouTube, não vou subir de novo."
        if motivo == MOTIVO_IMOVEL_NAO_ENCONTRADO:
            return f"Não encontrei o imóvel {codigo} no cadastro. Confira o código e mande de novo com o link."
        if para in RETENTAVEIS and not vai_retentar:
            if para == PARCIAL and resultado is not None:
                return (f"{len(resultado.falhos)} vídeo(s) do {codigo} não subiram ao YouTube, mesmo depois de tentar de novo. "
                        "Já avisei o responsável.")
            return f"Os vídeos do {codigo} não subiram ao YouTube, mesmo depois de tentar de novo. Já avisei o responsável."
        return None

    async def _postar_grupo(self, row: dict, texto: str) -> None:
        try:
            erro = await self._enviar_grupo(row["org_id"], row.get("connection_id"), row["chat_id"], texto)
        except Exception as exc:
            erro = f"envio_falhou: {type(exc).__name__}"
        if erro:
            logger.error("videos prontos: group message NOT sent submissao=%s (%s)", row.get("id"), erro)
            self._emitir(row["org_id"], "acao_falhou", {"acao": "video_pronto_aviso_grupo", "submissao_id": str(row.get("id")),
                                                        "motivo": erro[:80]})

    def listar(self, org_id: Any, limite: int = 50) -> list[dict]:
        return self.repo.listar(org_id, max(1, min(int(limite), 200)))


class SubmissaoNaoEncontrada(LookupError):
    pass


class RetryRecusado(Exception):
    def __init__(self, codigo: str, status: Any) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.status = status


# ─── the Supabase repository ────────────────────────────────────────────────
def transition_log_config() -> Any:
    """The aggregate rendered in migration 372 (`julia_video_pronto_events` + RPCs)."""
    from noctusai_lib.domain.transition_log import TransitionLogConfig

    return TransitionLogConfig(schema=SCHEMA, aggregate="julia_video_pronto", state_table=T_SUBMISSOES,
                               state_column="status", actor_kinds=("user", "agent", "system"))


class SupabaseSubmissoesRepo:
    """Over the schema-scoped service-role client. Status changes go through the transition log (row lock +
    compare-and-set + event in one transaction); every other field is a plain update."""

    def __init__(self, db: Any, log: Any = None) -> None:
        self.db = db
        if log is None:
            from noctusai_lib.domain.transition_log import make_transition_log

            log = make_transition_log("supabase", cfg=transition_log_config(), client=db)
        self.log = log

    def _um(self, q: Any) -> Optional[dict]:
        data = q.limit(1).execute().data or []
        return data[0] if data else None

    def config_ativa(self, connection_id: Any, chat_id: str) -> Optional[dict]:
        return self._um(self.db.table(T_CONFIG).select("*").eq("connection_id", str(connection_id))
                        .eq("chat_id", chat_id).eq("ativo", True))

    def config_da_org(self, org_id: Any) -> Optional[dict]:
        return self._um(self.db.table(T_CONFIG).select("*").eq("org_id", str(org_id)))

    def aberta(self, org_id: Any, chat_id: str, remetente: str) -> Optional[dict]:
        return self._um(self.db.table(T_SUBMISSOES).select("*").eq("org_id", str(org_id)).eq("chat_id", chat_id)
                        .eq("remetente", remetente).eq("status", AGUARDANDO))

    def mensagem_ja_vista(self, org_id: Any, chat_id: str, mensagem_id: str) -> bool:
        return self._um(self.db.table(T_SUBMISSOES).select("id").eq("org_id", str(org_id)).eq("chat_id", chat_id)
                        .contains("ids_mensagens", [mensagem_id])) is not None

    def obter(self, submissao_id: Any) -> Optional[dict]:
        return self._um(self.db.table(T_SUBMISSOES).select("*").eq("id", str(submissao_id)))

    def criar(self, org_id: Any, row: dict) -> Optional[dict]:
        outcome = self.log.create(str(org_id), row, actor_kind="agent", data={"origem": "grupo_videos_prontos"})
        if outcome.status == "refused":
            if outcome.code == "duplicate":  # another delivery opened the slot first (the open-slot UNIQUE index)
                return None
            raise RuntimeError(f"videos prontos: create refused ({outcome.code})")
        return self.obter((outcome.event or {}).get("entity_id"))

    def atualizar_aberta(self, submissao_id: Any, *, versao_esperada: int, campos: dict) -> bool:
        res = (self.db.table(T_SUBMISSOES).update(campos).eq("id", str(submissao_id)).eq("status", AGUARDANDO)
               .eq("versao", int(versao_esperada)).execute())
        return bool(res.data)

    def atualizar(self, submissao_id: Any, campos: dict) -> None:
        self.db.table(T_SUBMISSOES).update(campos).eq("id", str(submissao_id)).execute()

    def transicionar(self, org_id: Any, submissao_id: Any, *, de: str, para: str, evento: str, dados: dict,
                     ator_id: Optional[str] = None) -> bool:
        outcome = self.log.transition(str(org_id), str(submissao_id), from_state=de, to_state=para, event_type=evento,
                                      data={k: v for k, v in dados.items() if v is not None},
                                      actor_id=ator_id, actor_kind="user" if ator_id else "agent")
        if outcome.ok:
            return True
        if outcome.code != "stale_state":
            logger.error("videos prontos: transition %s->%s refused (%s) submissao=%s", de, para, outcome.code, submissao_id)
        return False

    def par_em_uso(self, org_id: Any, codigo: str, drive_folder_id: str, *, exceto: Any) -> Optional[dict]:
        return self._um(self.db.table(T_SUBMISSOES).select("id,status").eq("org_id", str(org_id)).eq("codigo", codigo)
                        .eq("drive_folder_id", drive_folder_id).in_("status", [PROCESSANDO, CONCLUIDO, PARCIAL])
                        .neq("id", str(exceto)))

    def jobs_do_lote(self, batch_id: Any) -> list[dict]:
        res = (self.db.table(T_UPLOAD_JOBS).select("id,status,youtube_video_id,target_format,file_name,created_at")
               .eq("batch_id", str(batch_id)).order("created_at").execute())
        return list(res.data or [])

    def listar(self, org_id: Any, limite: int) -> list[dict]:
        res = (self.db.table(T_SUBMISSOES).select("*").eq("org_id", str(org_id)).order("created_at", desc=True)
               .limit(int(limite)).execute())
        return list(res.data or [])


# ─── production wiring (built at FIRE time; every piece is a seam above) ────
def _scoped() -> Any:
    from app.dependencies import get_scoped_admin_client

    return get_scoped_admin_client(SCHEMA)


def build_upload_service() -> UploadPort:
    """The same `UploadService` the dashboard and the chat intake build, over the service-role client."""
    from noctusai_lib.integrations.redis import make_redis_client

    from app.config import settings
    from app.dependencies import get_admin_client
    from app.modules.youtube.services.upload import UPLOAD_DIR, UploadService
    from app.services.account_credentials import build_youtube_service_for_org
    from app.services.notification_service import build_notification_service

    admin = get_admin_client()
    redis_client = None
    try:
        redis_client = make_redis_client(settings.redis_url, decode_responses=True)
        redis_client.ping()
    except Exception as exc:
        logger.warning("videos prontos: Redis unavailable (%s) -- this upload bypasses the shared queue.", type(exc).__name__)
        redis_client = None
    return UploadService(
        user_supabase=admin, admin_supabase=admin, upload_dir=UPLOAD_DIR,
        youtube_service=build_youtube_service_for_org(admin, settings),
        notification_service=build_notification_service(admin, settings), redis_client=redis_client,
    )


def _resolver_metadados(org_id: Any, codigo: str, privacy_status: str) -> Any:
    from app.dependencies import get_admin_client
    from app.modules.youtube.services.upload_metadata import resolve_metadata_from_product_code

    return resolve_metadata_from_product_code(get_admin_client(), product_code=codigo, privacy_status=privacy_status,
                                              org_id=UUID(str(org_id)))


def _imovel_video_service() -> ImovelVideoPort:
    from app.services.imovel_video_youtube_service import build_imovel_video_youtube_service  # S1 (lands first)

    return build_imovel_video_youtube_service(_scoped())


async def _notificar_dono(org_id: Any, kind: str, assunto: str, texto: str) -> Any:
    from app.dependencies import get_admin_client
    from app.services.notification_service import build_notification_service

    return await build_notification_service(get_admin_client()).notify_video_pronto(
        org_id=UUID(str(org_id)), kind=kind, assunto=assunto, texto=texto)


async def enviar_no_grupo(org_id: Any, connection_id: Any, chat_id: str, texto: str) -> Optional[str]:
    """THE group send: the outbound gate (flow `interno`: a message to the org's own team, never to a lead), then the
    connection's WAHA line (paced by the seed WhatsApp rate limiter), the outbound row pre-written by `InternoSender` so
    the `fromMe` echo is never read as a human takeover. None on success, else the error label (nothing raises)."""
    from noctusai_lib.integrations.redis import make_redis_client

    from app.config import settings
    from app.dependencies import get_admin_client
    from app.services import julia_envio_gate
    from app.services.julia_linha import linha_da_conexao
    from app.services.julia_relatorio_service import InternoSender
    from app.services.message_store import MessageStore
    from app.services.whatsapp_connection_store import build_whatsapp_connection_store

    if not connection_id:
        return "sem_conexao"
    try:
        liberacao = julia_envio_gate.exigir(_scoped(), org_id, connection_id, julia_envio_gate.Fluxo.INTERNO)
    except julia_envio_gate.EnvioBloqueado as exc:  # already logged + `envio_bloqueado` event by the gate
        return f"bloqueado: {exc.motivo}"
    try:
        admin = get_admin_client()
        connection = build_whatsapp_connection_store(admin, encryption_key=settings.encryption_key).get_by_id(
            UUID(str(connection_id)), decrypt=True)
        if connection is None:
            return "conexao_nao_encontrada"
        sender = InternoSender(
            connection=connection, waha=linha_da_conexao(connection).waha_client(),
            redis=make_redis_client(settings.redis_url, decode_responses=True), liberacao=liberacao,
            message_store=MessageStore(admin_supabase=admin, org_id=UUID(str(org_id))),
        )
        await sender.send_reply(chat_id, texto)
    except Exception as exc:
        return f"envio_falhou: {type(exc).__name__}"
    return None


def _emitir_padrao(org_id: Any, tipo: str, payload: dict) -> Any:
    from app.services import julia_eventos_service

    return julia_eventos_service.emitir(_scoped(), org_id, tipo, None, payload)


def _jobs_padrao() -> JobsPort:
    from noctusai_lib.domain.jobs import make_job_repository

    from app.dependencies import get_admin_client

    return make_job_repository(supabase_client=get_admin_client(), schema_name=SCHEMA)


def build_service(*, jobs: Optional[JobsPort] = None, repo: Optional[SubmissoesRepo] = None) -> JuliaVideosProntosService:
    from app.config import settings

    return JuliaVideosProntosService(
        repo=repo or SupabaseSubmissoesRepo(_scoped()),
        jobs=jobs or _jobs_padrao(),
        upload_factory=build_upload_service,
        resolver_metadados=_resolver_metadados,
        imovel_video_factory=_imovel_video_service,
        notificar=_notificar_dono,
        enviar_grupo=enviar_no_grupo,
        emitir=_emitir_padrao,
        wait_seconds=settings.julia_youtube_upload_wait_seconds,
        retry_delay_seconds=settings.julia_youtube_retry_delay_seconds,
    )


# ─── the webhook entry (fire-and-forget from `whatsapp_router`) ─────────────
_CONFIG_TTL_S = 60.0
_config_cache: dict[tuple[str, str], tuple[float, Optional[dict]]] = {}


def _config_ativa_cached(repo: SubmissoesRepo, connection_id: Any, chat_id: str) -> Optional[dict]:
    """Every group message on the line asks "is this the Vídeos Prontos group?": answered from a 60 s in-process
    cache so a busy line does not pay one DB read per group message. Switching the config on/off lands within 60 s."""
    chave = (str(connection_id), chat_id)
    hit = _config_cache.get(chave)
    agora = time.monotonic()
    if hit is not None and agora - hit[0] < _CONFIG_TTL_S:
        return hit[1]
    cfg = repo.config_ativa(connection_id, chat_id)
    _config_cache[chave] = (agora, cfg)
    return cfg


def limpar_cache_config() -> None:
    _config_cache.clear()


async def ingerir_do_webhook(
    *, org_id: Any, connection_id: Any, chat_id: str, remetente: str, mensagem_id: Optional[str], texto: str,
    service_factory: Callable[[], JuliaVideosProntosService] = build_service, emitir: Optional[Emitir] = None,
) -> str:
    """A STORED group message. Not the Vídeos Prontos group of an active config -> "fora". Never raises: a failure is
    logged at ERROR and recorded as an `acao_falhou` event (the message itself is already durable in the inbox)."""
    try:
        if not extrair(texto).relevante:
            return "ignorada"
        service = service_factory()
        cfg = _config_ativa_cached(service.repo, connection_id, chat_id)
        if cfg is None or str(cfg.get("org_id")) != str(org_id):
            return "fora"
        return await service.receber(org_id=org_id, connection_id=connection_id, chat_id=chat_id, remetente=remetente,
                                     mensagem_id=mensagem_id, texto=texto)
    except Exception as exc:
        logger.exception("videos prontos: group message NOT ingested org=%s chat=%s", org_id, chat_id)
        try:
            (emitir or _emitir_padrao)(org_id, "acao_falhou", {"acao": "video_pronto_receber", "motivo": type(exc).__name__})
        except Exception as exc2:
            logger.error("videos prontos: could not record the ingest failure (%s)", type(exc2).__name__)
        return "erro"


# ─── job handlers (the dedicated worker, `julia_videos_prontos_worker`) ─────
def handlers(service_factory: Callable[[], JuliaVideosProntosService] = build_service) -> dict[str, Callable[[Any], Awaitable[None]]]:
    async def processar(job: Any) -> None:
        p = job.payload or {}
        out = await service_factory().processar(p["submissao_id"], int(p["versao"]))
        logger.info("videos prontos: processar submissao=%s v%s -> %s", p.get("submissao_id"), p.get("versao"), out)

    async def retry(job: Any) -> None:
        p = job.payload or {}
        out = await service_factory().retry(p["submissao_id"], int(p["tentativa"]), ator_id=p.get("ator_id"))
        logger.info("videos prontos: retry submissao=%s t%s -> %s", p.get("submissao_id"), p.get("tentativa"), out)

    async def executar(job: Any) -> None:
        p = job.payload or {}
        out = await service_factory().executar(p["submissao_id"])
        logger.info("videos prontos: executar submissao=%s -> %s", p.get("submissao_id"), out)

    return {JOB_PROCESSAR: processar, JOB_RETRY: retry, JOB_EXECUTAR: executar}


__all__ = [
    "CONCLUIDO", "ERROS", "Extracao", "FALHOU", "INCOMPLETO", "JOB_EXECUTAR", "JOB_PROCESSAR", "JOB_RETRY", "JOB_TYPES",
    "JuliaVideosProntosService", "PARCIAL", "PROCESSANDO", "RetryRecusado", "SEM_VIDEOS", "SubmissaoNaoEncontrada",
    "SupabaseSubmissoesRepo", "agregar", "build_service", "build_upload_service", "enviar_no_grupo", "extrair",
    "handlers", "ingerir_do_webhook", "limpar_cache_config", "transition_log_config",
]
