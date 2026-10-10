"""Lifecycle of the Pesquisa extraction worker (seed ``domain.jobs.Worker``).

A SECOND worker, deliberately separate from the edicao_fotos one: that worker's
``claim_gate`` is the fotos "processamento ativo" pause, which would also pause
Pesquisa. This one claims only ``pesquisa.extrair`` and has no gate; its single
switch is ``PESQUISA_EXTRACAO_WORKER_ENABLED`` (also read by submit -> 503).

Started from ``app/lifespan.py`` (second case of the lifespan-worker pattern
after edicao_fotos; at the third, ``ModuleRegistration`` should grow startup/
shutdown hooks). "When the process allows it": no Supabase service role (the
SQLite dev backend) logs why and keeps serving -- the worker is a side effect,
never a precondition for serving. The queue row lease keeps several processes
from running the same job.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import Any, Callable, Optional

from noctusai_lib.domain.jobs import DeadLetterError, Job, JobRepository, RetryPolicy, Worker, make_job_repository

from app.modules.media_creation.services.pesquisa_extracao_service import JOB_TYPE, executar_extracao
from app.modules.media_creation.services.pesquisa_service import PesquisaLlm, chat_pesquisa_llm

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
STOP_TIMEOUT_SECONDS = 10.0
#: 2 retries (contract 2.4), a few seconds apart: an infra blip, not a storm.
RETRY_POLICY = RetryPolicy(max_retries=2, backoff_seconds=5.0)

_task: Optional[asyncio.Task] = None
_stop: Optional[asyncio.Event] = None


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
    global _task, _stop
    if not cfg.pesquisa_extracao_worker_enabled:
        logger.info("pesquisa_extracao: worker DESLIGADO (PESQUISA_EXTRACAO_WORKER_ENABLED=false).")
        return False
    if _task is not None and not _task.done():
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
    _stop = asyncio.Event()
    _task = asyncio.create_task(worker.run_forever(stop_event=_stop), name="pesquisa-extracao-worker")
    logger.info("pesquisa_extracao: worker iniciado (%s).", worker_id())
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
        logger.warning("pesquisa_extracao: worker não parou em %.0fs — cancelando", STOP_TIMEOUT_SECONDS)
        _task.cancel()
    _task = _stop = None


def is_running() -> bool:
    return _task is not None and not _task.done()


__all__ = ["build_handler", "build_worker", "is_running", "make_jobs_repository", "start_worker", "stop_worker"]
