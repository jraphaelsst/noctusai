"""Lifecycle of the photo-editing job worker (seed `domain.jobs.Worker`).

Started from `app/lifespan.py` ONLY when `EDICAO_FOTOS_WORKER_ENABLED=true`.
Default OFF: every job the worker runs is an OpenAI call, and the account has
no credits (PROJECT.md §4c) — enabling it is the owner's switch. While it is
off, submitted batches simply wait in `social_wiring.jobs`.

One worker task per process; the job table's lease (`claim_next_job`) keeps
several processes from running the same job.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import Any, Optional

from noctusai_lib.domain.photo_editing import build_worker

from app.modules.edicao_fotos.services.ports import get_ports

logger = logging.getLogger(__name__)

STOP_TIMEOUT_SECONDS = 10.0

_task: Optional[asyncio.Task] = None
_stop: Optional[asyncio.Event] = None


def worker_id() -> str:
    return f"sw-edicao-fotos-{socket.gethostname()}-{os.getpid()}"


async def start_worker(cfg: Any) -> bool:
    """Start the worker if the flag is on. Returns whether it is running."""
    global _task, _stop
    if not cfg.edicao_fotos_worker_enabled:
        logger.info(
            "edicao_fotos: worker DESLIGADO (EDICAO_FOTOS_WORKER_ENABLED=false) — "
            "lotes submetidos ficam na fila até ser ligado."
        )
        return False
    if _task is not None and not _task.done():
        return True
    worker = build_worker(
        get_ports(cfg),
        worker_id=worker_id(),
        poll_interval_seconds=float(cfg.edicao_fotos_worker_poll_seconds),
    )
    _stop = asyncio.Event()
    _task = asyncio.create_task(worker.run_forever(stop_event=_stop), name="edicao-fotos-worker")
    logger.info("edicao_fotos: worker iniciado (%s)", worker_id())
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
        logger.warning("edicao_fotos: worker não parou em %.0fs — cancelando", STOP_TIMEOUT_SECONDS)
        _task.cancel()
    finally:
        _task = None
        _stop = None


def is_running() -> bool:
    return _task is not None and not _task.done()


__all__ = ["is_running", "start_worker", "stop_worker", "worker_id"]
