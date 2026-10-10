"""In-process transcription worker + retention sweeps (CONTRACT §3, §5).

* Seed jobs ``Worker``: concurrency 1, lease 300 s + heartbeat, ``max_retries=2``.
* ``TranscriberBusy`` -> ``RescheduleLater`` (does NOT consume a retry).
* The result write is idempotent on ``transcricao_id`` (compare-and-set from an
  active status), so a lease-reclaim re-run is harmless.
* Our-fault failures (transcriber unavailable / timeout / lost audio / storage)
  refund the minutes; a caller-fault rejection (undecodable audio) does not.
* Logs never carry transcript text or storage paths: one structured line per
  job, and handler-raised errors carry only a ``codigo``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

from noctusai_lib.domain.jobs import DeadLetterError, Job, JobRepository, RetryPolicy, Worker
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.integrations.transcription import (
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionError,
    TranscriptionRejected,
)

from app.services.transcription_api import limits as L
from app.services.transcription_api.repository import ACTIVE, iso, parse_ts
from app.services.transcription_api.service import TranscricaoService

logger = logging.getLogger(__name__)


class TranscricaoFalha(RuntimeError):
    """Retryable failure whose message is a bare ``codigo`` (safe to log)."""


def log_job(row: dict, *, status: str, codigo: Optional[str] = None, rtf: Optional[float] = None) -> None:
    """The one structured line per job (CONTRACT §5): id, org, caller_kind,
    bytes, duracao_s, rtf, wait_s, status, codigo. No text, no paths."""
    criado = parse_ts(row.get("criado_em"))
    iniciado = parse_ts(row.get("iniciado_em"))
    wait_s = round((iniciado - criado).total_seconds(), 1) if criado and iniciado else None
    logger.info(
        "transcricao.job id=%s org=%s caller_kind=%s bytes=%s duracao_s=%s rtf=%s wait_s=%s status=%s codigo=%s",
        row.get("id"), row.get("org_id"), row.get("caller_kind"), row.get("bytes"),
        row.get("duracao_s"), rtf, wait_s, status, codigo,
    )


class TranscricaoJobHandler:
    def __init__(
        self,
        service: TranscricaoService,
        *,
        clock: Callable[[], datetime],
        retry_policy: RetryPolicy,
        text_retention: timedelta = L.TEXT_RETENTION,
    ) -> None:
        self._s = service
        self._clock = clock
        self._policy = retry_policy
        self._text_retention = text_retention

    async def __call__(self, job: Job) -> None:
        s = self._s
        tid = (job.payload or {}).get("transcricao_id")
        if not tid:
            raise DeadLetterError("payload sem transcricao_id")
        row = s.repo.get(tid)
        if row is None or row["status"] not in ACTIVE:
            return  # cancelled / already finished / purged: nothing to do (idempotent)

        final_attempt = job.retry_count >= self._policy.max_retries
        now = self._clock()
        s.repo.transition(
            tid, from_status=ACTIVE,
            fields={"status": "processando", "iniciado_em": row.get("iniciado_em") or iso(now)},
        )
        row = s.repo.get(tid) or row

        blob = None
        if row.get("storage_path"):
            try:
                blob = await s.storage.get(bucket=L.BUCKET, key=row["storage_path"])
            except Exception as exc:  # noqa: BLE001 — storage hiccup: retry; only the type is logged (a message can carry the path)
                logger.error("transcricao.audio_read_failed id=%s err=%s", tid, type(exc).__name__)
                if final_attempt:
                    await s.falhar(tid, "armazenamento", reembolsar=True)
                    log_job(row, status="falhou", codigo="armazenamento")
                else:
                    s.repo.transition(tid, from_status=("processando",), fields={"status": "na_fila"})
                raise TranscricaoFalha("armazenamento")
        if blob is None:
            await s.falhar(tid, "audio_indisponivel", reembolsar=True)
            log_job(row, status="falhou", codigo="audio_indisponivel")
            raise DeadLetterError("audio_indisponivel")

        duracao_s = float(row["duracao_s"])
        try:
            transcriber = s.transcriber()
            result = await asyncio.wait_for(
                transcriber.transcribe(blob.data, language=row.get("idioma") or "pt", max_seconds=duracao_s),
                timeout=L.call_timeout_s(duracao_s),
            )
        except TranscriberBusy as exc:
            # Not a failure: back in line, retry budget untouched.
            s.repo.transition(tid, from_status=("processando",), fields={"status": "na_fila"})
            raise RescheduleLater(exc.retry_after_s, reason="transcriber_busy")
        except TranscriptionRejected as exc:
            # Caller's audio is undecodable: permanent, no refund.
            await s.falhar(tid, exc.codigo, reembolsar=False)
            log_job(row, status="falhou", codigo=exc.codigo)
            raise DeadLetterError(exc.codigo)
        except (TranscriberUnavailable, TranscriptionError, asyncio.TimeoutError) as exc:
            codigo = "tempo_excedido" if isinstance(exc, asyncio.TimeoutError) else "transcricao_indisponivel"
            s.transcriber_error = codigo
            logger.warning("transcricao.job_attempt_failed id=%s codigo=%s", tid, codigo)
            if final_attempt:
                await s.falhar(tid, codigo, reembolsar=True)
                log_job(row, status="falhou", codigo=codigo)
            else:
                s.repo.transition(tid, from_status=("processando",), fields={"status": "na_fila"})
            raise TranscricaoFalha(codigo)

        s.transcriber_error = None
        keep_segments = row.get("segmentos") is not None
        concluido = self._clock()
        applied = s.repo.transition(
            tid,
            from_status=ACTIVE,
            fields={
                "status": "concluida",
                "texto": result.text,
                "segmentos": (result.segmentos or []) if keep_segments else None,
                "modelo": result.modelo,
                "rtf": result.rtf,
                "concluido_em": iso(concluido),
                "expira_em": iso(concluido + self._text_retention),
            },
        )
        if not applied:
            return  # already concluded by an earlier run of this same job
        done = s.repo.get(tid) or row
        try:
            await s.apagar_audio(done)
        except Exception as exc:  # noqa: BLE001 — the 72 h sweep retries; never loses the result
            logger.error("transcricao.audio_delete_failed id=%s err=%s", tid, type(exc).__name__)
        log_job(done, status="concluida", rtf=result.rtf)


async def run_sweeps(service: TranscricaoService) -> dict:
    """Retention + stuck-job sweeps (CONTRACT §3, §5). Idempotent; each item
    is isolated so one failure never aborts the rest."""
    s = service
    now = s._clock()
    out = {"audio_apagado": 0, "texto_purgado": 0, "travados": 0, "erros": 0}

    for row in s.repo.audio_para_apagar(before=now - L.AUDIO_RETENTION_FAILED, limit=200):
        try:
            out["audio_apagado"] += int(await s.apagar_audio(row))
        except Exception as exc:  # noqa: BLE001 — type only: a storage message can carry the path
            out["erros"] += 1
            logger.error("transcricao.sweep_audio_failed id=%s err=%s", row.get("id"), type(exc).__name__)

    for row in s.repo.textos_expirados(now=now, limit=200):
        try:
            s.repo.update(row["id"], {"texto": None, "segmentos": None})
            out["texto_purgado"] += 1
        except Exception:  # noqa: BLE001
            out["erros"] += 1
            logger.exception("transcricao.sweep_text_failed id=%s", row.get("id"))

    # Oldest possible deadline is 6 h after creation, but a started job's
    # deadline is 3x duracao + 1 h after iniciado_em: pull everything older than
    # 1 h and apply the exact per-row deadline here.
    for row in s.repo.ativos_antigos(criado_antes=now - timedelta(hours=1), limit=200):
        try:
            started = parse_ts(row.get("iniciado_em"))
            if started is not None:
                deadline = started + L.stuck_deadline(row["duracao_s"], started=True)
            else:
                deadline = parse_ts(row["criado_em"]) + L.stuck_deadline(row["duracao_s"], started=False)
            if now >= deadline and await s.falhar(row["id"], "tempo_excedido", reembolsar=True):
                out["travados"] += 1
                log_job(row, status="falhou", codigo="tempo_excedido")
        except Exception:  # noqa: BLE001
            out["erros"] += 1
            logger.exception("transcricao.sweep_stuck_failed id=%s", row.get("id"))
    return out


def build_worker(service: TranscricaoService, jobs: JobRepository, *, worker_id: str = "core-transcricao-1") -> Worker:
    policy = RetryPolicy(max_retries=L.JOB_MAX_RETRIES, backoff_seconds=30.0, max_backoff_seconds=300.0)
    handler = TranscricaoJobHandler(service, clock=service._clock, retry_policy=policy)

    async def gate() -> bool:
        # Kill switch off: leave `na_fila` jobs untouched.
        return service.kill_switch.habilitada()

    return Worker(
        jobs,
        worker_id=worker_id,
        handlers={L.JOB_TYPE: handler},
        retry_policy=policy,
        poll_interval_seconds=L.POLL_INTERVAL_S,
        lease_seconds=L.LEASE_SECONDS,
        claim_gate=gate,
    )


class TranscricaoBackground:
    """Owns the worker loop + sweep ticker for one process."""

    def __init__(self, service: TranscricaoService, jobs: JobRepository) -> None:
        self.service = service
        self.worker = build_worker(service, jobs)
        self._stop: Optional[asyncio.Event] = None
        self._tasks: list[asyncio.Task] = []

    def running(self) -> bool:
        return bool(self._tasks) and all(not t.done() for t in self._tasks)

    async def start(self) -> None:
        if self._tasks:
            return
        self._stop = asyncio.Event()
        self._tasks = [
            asyncio.ensure_future(self._supervise("worker", self._run_worker)),
            asyncio.ensure_future(self._supervise("sweep", self._run_sweeps)),
        ]

    async def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks = []

    async def _run_worker(self) -> None:
        await self.worker.run_forever(stop_event=self._stop)

    async def _run_sweeps(self) -> None:
        while not self._stop.is_set():
            counts = await run_sweeps(self.service)
            logger.info("transcricao.sweep %s", counts)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=L.SWEEP_INTERVAL_S)
            except asyncio.TimeoutError:
                pass

    async def _supervise(self, name: str, run: Callable) -> None:
        """Restart a crashed loop (logged with traceback) instead of dying silent."""
        while not self._stop.is_set():
            try:
                await run()
                return
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("transcricao.%s_crashed — restarting in 10s", name)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass
