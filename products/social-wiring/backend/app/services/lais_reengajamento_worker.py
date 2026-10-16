"""Lifecycle of the Lais re-engagement worker (seed `domain.jobs.Worker`, wave 4).

Its OWN worker over the three job types of `lais_reengajamento_service` (a lead turn is an HTTP call to
agents; it must not queue behind -- or hold a lease of -- the Geracao / Biblioteca workers). Started and
stopped through the `ModuleRegistration` startup / shutdown hooks in `app/main.py`; "when the process
allows it": no Supabase admin client logs why and keeps serving -- a worker is a side effect, never a
precondition for serving. The queue row lease keeps several processes from running the same job.

The handler builds its `LeadDeps` at FIRE time from the conversation module (the Redis buffer lives
there); until that module exists the job reschedules itself rather than failing.
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any, Optional

from noctusai_lib.domain.jobs import JobRepository, RetryPolicy, Worker, make_job_repository
from noctusai_lib.domain.jobs.lifecycle import WorkerHandle

from app.services import lais_credito_service, lais_envio_service, lais_reengajamento_service as svc

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
STOP_TIMEOUT_SECONDS = 10.0
RETRY_POLICY = RetryPolicy(max_retries=svc.JOB_MAX_RETRIES, backoff_seconds=30.0)

_handle: Optional[WorkerHandle] = None


def worker_id() -> str:
    return f"sw-lais-reengajamento-{socket.gethostname()}-{os.getpid()}"


def _lead_deps_factory(cfg: Any):
    def build() -> Any:
        from app.services.conversation_module import get_conversation_module
        from app.services.lais_lead_turn_service import LeadDeps

        module = get_conversation_module()
        if module is None:
            return None
        return LeadDeps(buffer=module.buffer, admin=module.admin_supabase, cfg=cfg)

    return build


def build_worker(repo: JobRepository, cfg: Any) -> Worker:
    from app.services.lais_lead_turn_service import run_reengajamento_turn

    # the cold-lead hook (end of the last attempt) arms `lais_envio_frio` on THIS repo; the same worker fires it
    lais_envio_service.registrar_repo(repo)
    lais_credito_service.registrar_repo(repo)  # the credit analysis (wave 13) is queued on the same repo
    return Worker(
        repo,
        worker_id=worker_id(),
        handlers={
            **svc.handlers(deps_factory=_lead_deps_factory(cfg), repo=repo, run_turn=run_reengajamento_turn),
            **lais_envio_service.handlers(),
            **lais_credito_service.handlers(),
        },
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=float(cfg.lais_reengajamento_poll_seconds),
        lease_seconds=float(cfg.lais_reengajamento_lease_seconds),
    )


def is_running() -> bool:
    return _handle is not None and _handle.is_running()


async def start_worker(cfg: Any = None, *, db: Any = None, repo: Optional[JobRepository] = None) -> bool:
    """Start the worker. Returns whether it is running."""
    if cfg is None:
        from app.config import settings as cfg
    global _handle
    if not cfg.lais_reengajamento_worker_enabled:
        logger.info("lais reengajamento: worker DESLIGADO (LAIS_REENGAJAMENTO_WORKER_ENABLED=false).")
        return False
    if is_running():
        return True
    if repo is None:
        if db is None:
            from app.dependencies import _use_sqlite, get_admin_client

            if _use_sqlite:
                logger.warning("lais reengajamento: worker não iniciado — requer o Supabase (backend sqlite).")
                return False
            db = get_admin_client()
        if db is None:
            logger.warning("lais reengajamento: worker não iniciado — sem cliente admin do Supabase.")
            return False
        repo = make_job_repository(supabase_client=db, schema_name=SCHEMA)
    _handle = WorkerHandle(build_worker(repo, cfg), name="lais-reengajamento-worker", stop_timeout=STOP_TIMEOUT_SECONDS)
    _handle.start()
    logger.info("lais reengajamento: worker iniciado (%s).", worker_id())
    return True


async def stop_worker() -> None:
    global _handle
    handle, _handle = _handle, None
    if handle is not None:
        await handle.stop()


async def startup_hook() -> None:
    """`ModuleRegistration.startup`: a failure is logged at ERROR and never aborts startup."""
    try:
        await start_worker()
    except Exception:
        logger.exception("lais reengajamento: worker NÃO iniciado — os timers ficam na fila.")


__all__ = ["build_worker", "is_running", "start_worker", "startup_hook", "stop_worker"]
