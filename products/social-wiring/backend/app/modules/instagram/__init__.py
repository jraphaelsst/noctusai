"""``instagram`` — Instagram Business Login insights module.

Per-post catalog + daily per-post / per-account snapshots for
``provider="instagram"`` integration accounts (migration
``208_instagram_insights.sql``), the daily ``instagram_daily_snapshot`` job,
and the ``/api/instagram/accounts/{account_id}/...`` read + sync surface.
Contract: ``projects/core-studio/specs/instagram-insights-api.md``.

Provider data comes from the seed Instagram-Login adapter
(``noctusai_lib.integrations.meta.instagram_login_adapter`` — Protocol +
Real + Fake + ``get_instagram_login_adapter``).
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    from app.main import ModuleRegistration
    from app.modules.instagram.router import router
    from app.modules.instagram.scheduler import configure as _configure_scheduler

    # Register the daily job before the lifespan starts the scheduler.
    _configure_scheduler()
    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
