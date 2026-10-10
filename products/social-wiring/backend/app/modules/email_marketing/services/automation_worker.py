"""The automation-step seed ``Worker`` (handler ``email_marketing.automation_step``) and its
``WorkerHandle`` lifecycle, started / stopped by the ``email_marketing`` module startup / shutdown
hooks. Same shape as ``transcricoes.biblioteca_worker``."""
from __future__ import annotations

import logging
import os
import socket
from typing import Any, Optional

from noctusai_lib.domain.jobs import JobRepository, RetryPolicy, Worker, make_job_repository
from noctusai_lib.domain.jobs.lifecycle import WorkerHandle

from app.modules.email_marketing.services.automation_executor import JOB_TYPE, build_handler

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
STOP_TIMEOUT_SECONDS = 10.0
#: An infra blip retries a couple of times; malformed config is a DeadLetterError (no retries).
RETRY_POLICY = RetryPolicy(max_retries=3, backoff_seconds=5.0)

_handle: Optional[WorkerHandle] = None


def worker_id() -> str:
    return f"sw-email-automation-{socket.gethostname()}-{os.getpid()}"


def make_jobs_repository(db: Any) -> JobRepository:
    return make_job_repository(supabase_client=db, schema_name=SCHEMA)


def build_worker(repo: JobRepository, db: Any, cfg: Any) -> Worker:
    return Worker(
        repo,
        worker_id=worker_id(),
        handlers={JOB_TYPE: build_handler(db, repo)},
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=float(getattr(cfg, "email_automation_poll_seconds", 5.0)),
        lease_seconds=float(getattr(cfg, "email_automation_lease_seconds", 120.0)),
    )


async def start_worker(cfg: Any, *, db: Any = None, repo: Optional[JobRepository] = None) -> bool:
    """Start the worker. Returns whether it is running."""
    global _handle
    if not getattr(cfg, "email_automation_worker_enabled", True):
        logger.info("email_marketing: automation worker DESLIGADO (EMAIL_AUTOMATION_WORKER_ENABLED=false).")
        return False
    if is_running():
        return True
    if db is None:
        from app.dependencies import _use_sqlite, get_admin_client

        if _use_sqlite:
            logger.warning("email_marketing: automation worker não iniciado — requer o Supabase (backend sqlite).")
            return False
        db = get_admin_client()
    if db is None:
        logger.warning("email_marketing: automation worker não iniciado — sem cliente admin do Supabase.")
        return False
    worker = build_worker(repo or make_jobs_repository(db), db, cfg)
    _handle = WorkerHandle(worker, name="email-automation-worker", stop_timeout=STOP_TIMEOUT_SECONDS)
    _handle.start()
    logger.info("email_marketing: automation worker iniciado (%s).", worker_id())
    return True


async def stop_worker() -> None:
    global _handle
    handle, _handle = _handle, None
    if handle is not None:
        await handle.stop()


def is_running() -> bool:
    return _handle is not None and _handle.is_running()


__all__ = ["build_worker", "is_running", "make_jobs_repository", "start_worker", "stop_worker"]
