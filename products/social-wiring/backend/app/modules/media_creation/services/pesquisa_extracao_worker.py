"""Lifecycle of the Pesquisa extraction worker (seed ``domain.jobs.Worker``).

A SECOND worker, deliberately separate from the edicao_fotos one: that worker's
``claim_gate`` is the fotos "processamento ativo" pause, which would also pause
Pesquisa. This one claims only ``pesquisa.extrair`` and has no gate; its single
switch is ``PESQUISA_EXTRACAO_WORKER_ENABLED`` (also read by submit -> 503).

Started/stopped through the ``ModuleRegistration`` startup/shutdown hooks
(``media_creation.register()``), over the seed ``WorkerHandle``. "When the process allows it": no Supabase service role (the
SQLite dev backend) logs why and keeps serving -- the worker is a side effect,
never a precondition for serving. The queue row lease keeps several processes
from running the same job.
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any, Callable, Optional

from noctusai_lib.domain.jobs import DeadLetterError, Job, JobRepository, RetryPolicy, Worker, make_job_repository
from noctusai_lib.domain.jobs.lifecycle import WorkerHandle

from app.modules.media_creation.services.pesquisa_extracao_service import JOB_TYPE, executar_extracao
from app.modules.media_creation.services.pesquisa_service import PesquisaLlm, chat_pesquisa_llm

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
STOP_TIMEOUT_SECONDS = 10.0
#: 2 retries (contract 2.4), a few seconds apart: an infra blip, not a storm.
RETRY_POLICY = RetryPolicy(max_retries=2, backoff_seconds=5.0)

_handle: Optional[WorkerHandle] = None


def worker_id() -> str:
    return f"sw-pesquisa-extracao-{socket.gethostname()}-{os.getpid()}"


def make_jobs_repository(db) -> JobRepository:
    """The queue repo over the ``social_wiring``-default admin client."""
    return make_job_repository(supabase_client=db, schema_name=SCHEMA)


def build_handler(db, llm: PesquisaLlm, cfg: Any) -> Callable[[Job], Any]:
    async def handle(job: Job) -> None:
        extracao_id = (job.payload or {}).get("extracao_id")
        if not extracao_id:
            raise DeadLetterError("payload sem extracao_id")
        await executar_extracao(
            db, llm, str(extracao_id),
            texto_max_chars=int(cfg.pesquisa_extracao_texto_max_chars),
        )

    return handle


def build_worker(repo: JobRepository, db, cfg: Any, llm: PesquisaLlm = chat_pesquisa_llm) -> Worker:
    return Worker(
        repo,
        worker_id=worker_id(),
        handlers={JOB_TYPE: build_handler(db, llm, cfg)},
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=float(cfg.pesquisa_extracao_poll_seconds),
        lease_seconds=float(cfg.pesquisa_extracao_lease_seconds),
    )


async def start_worker(cfg: Any, *, db: Any = None, repo: Optional[JobRepository] = None) -> bool:
    """Start the worker. Returns whether it is running."""
    global _handle
    if not cfg.pesquisa_extracao_worker_enabled:
        logger.info("pesquisa_extracao: worker DESLIGADO (PESQUISA_EXTRACAO_WORKER_ENABLED=false).")
        return False
    if is_running():
        return True
    if db is None:
        from app.dependencies import _use_sqlite, get_admin_client

        if _use_sqlite:
            logger.warning("pesquisa_extracao: worker não iniciado — requer o Supabase (backend sqlite).")
            return False
        db = get_admin_client()
    if db is None:
        logger.warning("pesquisa_extracao: worker não iniciado — sem cliente admin do Supabase.")
        return False
    worker = build_worker(repo or make_jobs_repository(db), db, cfg)
    _handle = WorkerHandle(worker, name="pesquisa-extracao-worker", stop_timeout=STOP_TIMEOUT_SECONDS)
    _handle.start()
    logger.info("pesquisa_extracao: worker iniciado (%s).", worker_id())
    return True


async def stop_worker() -> None:
    global _handle
    handle, _handle = _handle, None
    if handle is not None:
        await handle.stop()


def is_running() -> bool:
    return _handle is not None and _handle.is_running()


__all__ = ["build_handler", "build_worker", "is_running", "make_jobs_repository", "start_worker", "stop_worker"]
