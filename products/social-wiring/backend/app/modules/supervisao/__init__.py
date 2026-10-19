"""`supervisao` — Maya, the supervisor agent (maya-blocks CONTRACT §2.3 / §3 / §4.3-4.5, slice S3).

- `metricas`  — deterministic scorecard engine (rubric `sdr.v1` for Julia, `<bloco>.v1` for human blocks).
- `service`   — config, nightly scorecard upsert, handoff sweep (assumido/expirado), read models.
- `relatorio` — the owner-only daily report: `relatorio` lais_evento + `SupervisaoDigestService` email.
- `scheduler` — 07:00 America/Sao_Paulo nightly job + 15-min handoff sweep (seed scheduler).
- `router`    — GET /api/supervisao/scorecards · GET /api/supervisao/handoffs · GET/PUT /api/supervisao/config.

Read-only toward leads: nothing here sends to a lead or writes leads, cards or chats (CONTRACT §5).
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Configures both scheduler jobs at import time — before `start_scheduler()` fires in
    `app/lifespan.py`, the only moment they can be registered.
    """
    from app.main import ModuleRegistration
    from app.modules.supervisao import scheduler
    from app.modules.supervisao.router import router

    scheduler.configure()
    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
