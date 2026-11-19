"""``worker criacao`` -- the CoreStudio media worker, a SEPARATE process of the same image (contract section 5).

    python -m app.modules.media_creation.criacao_worker

It claims only ``media.step`` jobs (the seed ``MediaGraphRunner``'s job type), one at a time: ONE render slot per worker
process (a render is CPU-bound and shares the VPS with the API). It never runs inside the API process, so a render can
never starve a request. Restart-safe: every job's payload carries its graph (inputs + quota estimate) and the ledger
holds the state, so a killed worker's leased job is re-claimed and resumed.

Deploy shape (NOT declared in deploy/fleet/docker-compose.prod.yml here: registering a new prod service is the owner's
prod-exposure decision, gated by ``noctus.dev.prod_consent``): a service of the SAME image as ``social-wiring``
(``<<: *prod-defaults``), ``command: ["python", "-m", "app.modules.media_creation.criacao_worker"]``, ``profiles: [criacao]``,
no port / healthcheck, ``oom_score_adj: 800``, ``stop_grace_period: 60s``. It needs migrations 362-367 applied, the platform
ElevenLabs key and a marca voice consent first.

A graceful stop (SIGTERM / SIGINT) lets the current step finish within the stop timeout.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from typing import Any, Optional

from noctusai_lib.domain.jobs import RetryPolicy, Worker
from noctusai_lib.domain.media_production import JOB_TYPE

logger = logging.getLogger(__name__)

#: the stepper owns its retries (``max_retries`` of the runner); the seed worker's policy matches it.
RETRY_POLICY = RetryPolicy(max_retries=2, backoff_seconds=15.0)


def worker_id() -> str:
    return f"sw-criacao-{socket.gethostname()}-{os.getpid()}"


def build_worker(db: Any, cfg: Any, *, jobs: Any = None, bus: Any = None, deps: Any = None) -> Worker:
    """The worker over the product's runner. ``jobs`` / ``bus`` / ``deps`` are the DI seams (tests pass Fakes)."""
    from app.modules.media_creation.services import criacao_service as cs
    from app.modules.media_creation.services.geracao_jobs import make_jobs_repository

    jobs = jobs or make_jobs_repository(db)
    runner = cs.make_runner(db, jobs, bus or cs.progress_bus(), deps or cs.default_deps(db), max_retries=RETRY_POLICY.max_retries)
    # poll-budget: claim poll, 5s base doubling to the 300s seed cap when idle, reset on work; 1 calls/tick (rpc claim_next_job); worst 288/day per idle worker (17280/day only while busy at the 5s base); idle=backoff
    return Worker(
        jobs,
        worker_id=worker_id(),
        handlers=runner.handlers,
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=float(cfg.criacao_worker_poll_seconds),
        lease_seconds=float(cfg.criacao_worker_lease_seconds),
    )


async def run(stop: Optional[asyncio.Event] = None) -> None:
    from app.config import settings
    from app.dependencies import get_admin_client

    db = get_admin_client()
    if db is None:
        raise RuntimeError("worker criacao: sem cliente admin do Supabase — o worker não pode iniciar")
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    worker = build_worker(db, settings)
    logger.info("criacao: worker iniciado (%s) — job type %s.", worker_id(), JOB_TYPE)
    await worker.run_forever(stop_event=stop)
    logger.info("criacao: worker encerrado.")


def main() -> None:
    from app.logging_config import configure_logging  # same structured logging as the API process

    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
