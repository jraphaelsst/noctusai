"""Lifecycle of the Julia "Vídeos Prontos" worker (seed `domain.jobs.Worker`).

Its OWN worker over `julia_videos_prontos.processar` / `.retry` (`julia_videos_prontos_service`): one job runs a whole
Drive folder through the YouTube upload (download + upload + processing wait per video, minutes), so it must never hold
the lease of -- or queue in front of -- the re-engagement worker's lead turns. Started / stopped through the
`ModuleRegistration` startup / shutdown hooks in `app/main.py`; a worker is a side effect, never a precondition for
serving.

🔴 It uploads to the org's YouTube channel and posts in a real WhatsApp group, so it starts only where the seed's
`schedulers_enabled()` holds (`NOCTUS_SCHEDULERS_ENABLED`, carried only by the deployed container's compose block).
`JULIA_VIDEOS_PRONTOS_WORKER_ENABLED=false` is the per-deploy kill switch on top.
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any, Optional

from noctusai_lib.api.scheduler import SCHEDULERS_ENABLED_ENV, schedulers_enabled
from noctusai_lib.domain.jobs import JobRepository, RetryPolicy, Worker, make_job_repository
from noctusai_lib.domain.jobs.lifecycle import WorkerHandle

from app.services import julia_videos_prontos_service as svc

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
STOP_TIMEOUT_SECONDS = 10.0
#: the service closes every submission itself (never leaves it `processando`); a handler crash is retried once
RETRY_POLICY = RetryPolicy(max_retries=1, backoff_seconds=60.0)
POLL_SECONDS = 5.0
#: a folder of several videos takes minutes; the heartbeat renews the lease while the handler runs
LEASE_SECONDS = 900.0

_handle: Optional[WorkerHandle] = None


def worker_id() -> str:
    return f"sw-julia-videos-prontos-{socket.gethostname()}-{os.getpid()}"


def build_worker(repo: JobRepository) -> Worker:
    # poll-budget: claim poll, 5s base doubling to the 300s seed cap when idle, reset on work; 1 calls/tick (rpc claim_next_job); worst 288/day per idle worker (17280/day only while busy at the 5s base); idle=backoff
    return Worker(
        repo,
        worker_id=worker_id(),
        handlers=svc.handlers(service_factory=lambda: svc.build_service(jobs=repo)),
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=POLL_SECONDS,
        lease_seconds=LEASE_SECONDS,
    )


def is_running() -> bool:
    return _handle is not None and _handle.is_running()


async def start_worker(cfg: Any = None, *, db: Any = None, repo: Optional[JobRepository] = None) -> bool:
    """Start the worker. Returns whether it is running."""
    if cfg is None:
        from app.config import settings as cfg
    global _handle
    if not cfg.julia_videos_prontos_worker_enabled:
        logger.info("julia videos prontos: worker DESLIGADO (JULIA_VIDEOS_PRONTOS_WORKER_ENABLED=false).")
        return False
    if not schedulers_enabled():
        logger.info("julia videos prontos: worker DESLIGADO (%s ausente -- só o container implantado envia).", SCHEDULERS_ENABLED_ENV)
        return False
    if is_running():
        return True
    if repo is None:
        if db is None:
            from app.dependencies import _use_sqlite, get_admin_client

            if _use_sqlite:
                logger.warning("julia videos prontos: worker não iniciado — requer o Supabase (backend sqlite).")
                return False
            db = get_admin_client()
        if db is None:
            logger.warning("julia videos prontos: worker não iniciado — sem cliente admin do Supabase.")
            return False
        repo = make_job_repository(supabase_client=db, schema_name=SCHEMA)
    _handle = WorkerHandle(build_worker(repo), name="julia-videos-prontos-worker", stop_timeout=STOP_TIMEOUT_SECONDS)
    _handle.start()
    logger.info("julia videos prontos: worker iniciado (%s).", worker_id())
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
    except Exception as exc:
        logger.error("julia videos prontos: worker NÃO iniciado — as submissões ficam na fila. (%s)", type(exc).__name__)


__all__ = ["build_worker", "is_running", "start_worker", "startup_hook", "stop_worker"]
