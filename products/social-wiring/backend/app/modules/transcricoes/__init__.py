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

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`."""
    from app.modules.transcricoes import scheduler
    from app.modules.transcricoes.router import router

    from app.main import ModuleRegistration

    # Import-time registration, BEFORE `start_scheduler()` — the retention sweep.
    scheduler.configure()
    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
