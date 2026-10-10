"""The transcription job worker (seed ``domain.jobs.Worker``) and its handler.

Its OWN worker (concurrency 1, lease 300 s with heartbeat), started/stopped from
``app/lifespan.py`` like the Pesquisa extraction one. The kill switch
``transcricao_habilitada`` is the worker's ``claim_gate``: while off, jobs stay
``pending`` untouched.

Handler outcomes (transcription-contract.md section 2):
- success: transcript persisted, audio DELETED at once (``audio_apagado_em``),
  the context's completion hook runs exactly once.
- ``TranscriberBusy``: ``RescheduleLater`` — the queue row goes back to pending
  WITHOUT consuming a retry (and the row is shown as queued again).
- ``TranscriptionRejected``: permanent (the user's audio) -> failed, no refund.
- ``TranscriberUnavailable``: retried with backoff; once retries are exhausted ->
  failed + refunded (our fault).
- Idempotent on ``transcricao_id``: a job that finds its row already terminal
  returns; one that finds it ``concluida`` with the hook pending only re-runs the hook.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime
from typing import Any, Callable, Optional

from noctusai_lib.domain.jobs import (
    DeadLetterError,
    Job,
    JobRepository,
    RetryPolicy,
    Worker,
)
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.transcription import (
    DEFAULT_LIMITS,
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionError,
    TranscriptionNotConfigured,
    TranscriptionRejected,
)

from app.modules.transcricoes import hooks
from app.modules.transcricoes.deps import (
    BUCKET,
    CachedSwitch,
    KillSwitch,
    TranscriberFactory,
    make_jobs_repository,
    read_kill_switch,
)
from app.modules.transcricoes.service import JOB_TYPE, TABLE, apagar_audio, iso, load_row, marcar_falha, now

logger = logging.getLogger(__name__)

STOP_TIMEOUT_SECONDS = 10.0
#: 2 retries (contract section 2), a few seconds apart. Busy never reaches this.
RETRY_POLICY = RetryPolicy(max_retries=2, backoff_seconds=30.0)
# The per-job hard cap (min(1800, 3 x duracao) + 60 s) is the Real transcriber
# client's timeout (``LocalWhisperTranscriber``); the lease heartbeat covers the wait.

_task: Optional[asyncio.Task] = None
_stop: Optional[asyncio.Event] = None


def worker_id() -> str:
    return f"sw-transcricao-{socket.gethostname()}-{os.getpid()}"


def _log_job(row: dict[str, Any], job: Job, status: str, codigo: Optional[str] = None) -> None:
    """The one structured line per job. Never the transcript, never a path."""
    wait_s = None
    try:
        if row.get("criado_em") and row.get("iniciado_em"):
            wait_s = round(
                (datetime.fromisoformat(str(row["iniciado_em"])) - datetime.fromisoformat(str(row["criado_em"]))).total_seconds(), 1
            )
    except ValueError:
        pass
    logger.info(
        "transcricao.job job_id=%s id=%s org=%s user=%s bytes=%s duracao_s=%s rtf=%s wait_s=%s status=%s codigo=%s",
        job.id, row.get("id"), row.get("org_id"), row.get("user_id"), row.get("bytes"),
        row.get("duracao_s"), row.get("rtf"), wait_s, status, codigo,
    )


def run_hook(db: Any, row: dict[str, Any]) -> None:
    """Run the context's completion hook exactly once: claim ``hook_aplicado_em``
    atomically, apply, release the claim if the hook raises (so a retry re-runs it)."""
    handler = hooks.get_contexto(row["contexto_tipo"])
    if handler is None:
        logger.error("transcricoes: no completion hook for contexto_tipo=%s (id=%s)", row["contexto_tipo"], row["id"])
        return
    claimed = (
        db.table(TABLE).update({"hook_aplicado_em": iso()})
        .eq("id", row["id"]).is_("hook_aplicado_em", "null").execute().data
    )
    if not claimed:
        return  # another run already applied it
    try:
        handler.aplicar(db, row)
    except Exception:
        db.table(TABLE).update({"hook_aplicado_em": None}).eq("id", row["id"]).execute()
        raise


def build_handler(
    db: Any, storage: StorageBackend, transcriber_factory: TranscriberFactory
) -> Callable[[Job], Any]:
    async def handle(job: Job) -> None:
        transcricao_id = (job.payload or {}).get("transcricao_id")
        if not transcricao_id:
            raise DeadLetterError("payload sem transcricao_id")
        row = load_row(db, str(transcricao_id))
        if row is None:
            raise DeadLetterError("transcricao inexistente")
        status = row["status"]
        if status == "concluida":
            if not row.get("hook_aplicado_em"):
                run_hook(db, row)  # a previous run died between persisting and the hook
            return
        if status in ("falhou", "cancelada"):
            return  # cancelled while queued / failed by the sweep: nothing to do
        if status == "na_fila":
            claimed = (
                db.table(TABLE).update({"status": "processando", "iniciado_em": iso()})
                .eq("id", row["id"]).eq("status", "na_fila").execute().data
            )
            if not claimed:
                return  # lost the race to a cancel
            row = {**row, "status": "processando", "iniciado_em": iso()}

        blob = await storage.get(bucket=BUCKET, key=row["storage_path"])
        if blob is None:
            marcar_falha(db, row["id"], "audio_ausente", reembolsar=True)
            _log_job(row, job, "falhou", "audio_ausente")
            raise DeadLetterError("audio ausente")
        try:
            transcriber = transcriber_factory()
            result = await transcriber.transcribe(
                blob.data, language="pt", max_seconds=DEFAULT_LIMITS.max_duration_s
            )
        except TranscriberBusy as exc:
            _volta_para_fila(db, row)
            raise RescheduleLater(exc.retry_after_s, "transcriber busy") from exc
        except TranscriptionRejected as exc:
            marcar_falha(db, row["id"], exc.codigo or "audio_corrompido", reembolsar=False)
            _log_job(row, job, "falhou", exc.codigo)
            raise DeadLetterError(f"rejeitado: {exc.codigo}") from exc
        except (TranscriberUnavailable, TranscriptionNotConfigured, TranscriptionError) as exc:
            if job.retry_count >= RETRY_POLICY.max_retries:
                marcar_falha(db, row["id"], "transcricao_indisponivel", reembolsar=True)
                _log_job(row, job, "falhou", "transcricao_indisponivel")
                raise DeadLetterError("transcriber indisponivel") from exc
            _volta_para_fila(db, row)
            raise
        # Persist the transcript FIRST, then delete the audio, then the hook.
        patch = {
            "status": "concluida", "texto": result.text, "modelo": result.modelo,
            "rtf": result.rtf, "concluido_em": iso(),
        }
        db.table(TABLE).update(patch).eq("id", row["id"]).execute()
        row = {**row, **patch}
        await apagar_audio(db, storage, row)
        _log_job(row, job, "concluida")
        run_hook(db, row)

    return handle


def _volta_para_fila(db: Any, row: dict[str, Any]) -> None:
    """The job will run again: show it as queued, not as 'processing'."""
    db.table(TABLE).update({"status": "na_fila"}).eq("id", row["id"]).eq("status", "processando").execute()


def build_worker(
    repo: JobRepository, db: Any, storage: StorageBackend, cfg: Any,
    transcriber_factory: TranscriberFactory, kill_switch: KillSwitch = read_kill_switch,
) -> Worker:
    gate = CachedSwitch(kill_switch, float(cfg.transcricao_gate_ttl_seconds))

    async def claim_gate() -> bool:
        return await asyncio.to_thread(gate)

    return Worker(
        repo,
        worker_id=worker_id(),
        handlers={JOB_TYPE: build_handler(db, storage, transcriber_factory)},
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=float(cfg.transcricao_poll_seconds),
        lease_seconds=float(cfg.transcricao_lease_seconds),
        claim_gate=claim_gate,
    )


async def start_worker(
    cfg: Any, *, db: Any = None, repo: Optional[JobRepository] = None,
    storage: Optional[StorageBackend] = None, transcriber_factory: Optional[TranscriberFactory] = None,
) -> bool:
    """Start the worker. Returns whether it is running."""
    global _task, _stop
    if not cfg.transcricao_worker_enabled:
        logger.info("transcricoes: worker DESLIGADO (TRANSCRICAO_WORKER_ENABLED=false).")
        return False
    if _task is not None and not _task.done():
        return True
    if db is None:
        from app.dependencies import _use_sqlite, get_admin_client

        if _use_sqlite:
            logger.warning("transcricoes: worker não iniciado — requer o Supabase (backend sqlite).")
            return False
        db = get_admin_client()
    if db is None:
        logger.warning("transcricoes: worker não iniciado — sem cliente admin do Supabase.")
        return False
    if storage is None:
        from app.modules.certidoes.deps import storage_for

        storage = storage_for(db)
    if transcriber_factory is None:
        from noctusai_lib.integrations.transcription import make_transcriber

        transcriber_factory = make_transcriber
    worker = build_worker(repo or make_jobs_repository(db), db, storage, cfg, transcriber_factory)
    _stop = asyncio.Event()
    _task = asyncio.create_task(worker.run_forever(stop_event=_stop), name="transcricao-worker")
    logger.info("transcricoes: worker iniciado (%s).", worker_id())
    return True


async def stop_worker() -> None:
    global _task, _stop
    if _task is None:
        return
    assert _stop is not None
    _stop.set()
    try:
        await asyncio.wait_for(_task, timeout=STOP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("transcricoes: worker não parou em %.0fs — cancelando", STOP_TIMEOUT_SECONDS)
        _task.cancel()
    _task = _stop = None


def is_running() -> bool:
    return _task is not None and not _task.done()


__all__ = ["build_handler", "build_worker", "is_running", "run_hook", "start_worker", "stop_worker"]
