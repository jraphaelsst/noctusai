"""``transcricoes`` — the shared voice-transcription product layer of social-wiring.

One table (``social_wiring.transcricoes``, migration 225), one queue type
(``jobs.type='transcricao'``), one worker, one set of quotas — for every consumer
(today: Segundo Cérebro voice answers; later: YouTube / extractions). A consumer
registers a ``contexto_tipo`` through :mod:`app.modules.transcricoes.hooks`
(ownership check + completion hook); it never owns a transcription table.

Why a top-level module and not under ``media_creation``: the contract makes this a
SHARED layer (``contexto_tipo`` is a registry), so it must not depend on any one
consumer — ``media_creation`` depends on it, not the reverse.

Spec: ``projects/core-studio/specs/transcription-contract.md``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`."""
    from app.modules.transcricoes import scheduler
    from app.modules.transcricoes.router import router

    from app.main import ModuleRegistration

    # Import-time registration, BEFORE `start_scheduler()` — the retention sweep.
    scheduler.configure()

    async def start_worker_hook() -> None:
        """Its OWN seed Worker (type "transcricao", concurrency 1, lease 300 s, heartbeat). Its
        claim gate is the kill switch `transcricao_habilitada` (default OFF): while off, jobs
        stay pending."""
        from app.config import settings
        from app.modules.transcricoes.worker import start_worker

        try:
            await start_worker(settings)
        except Exception:
            logger.exception("transcricoes: worker NÃO iniciado — as transcrições ficam na fila.")

    async def stop_worker_hook() -> None:
        from app.modules.transcricoes.worker import stop_worker

        await stop_worker()

    return ModuleRegistration(
        routers=[router],
        standard_routers=(),
        startup=[start_worker_hook],
        shutdown=[stop_worker_hook],
    )


__all__ = ["register"]
