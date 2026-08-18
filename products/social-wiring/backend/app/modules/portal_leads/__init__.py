"""``portal_leads`` — inbound real-estate-portal lead ingestion.

Today: **Grupo OLX** (ZAP · VivaReal · OLX · ImovelWeb · Casa Mineira),
which share a single webhook. Named for the category rather than the
vendor because the next portal outside the OLX group (a direct ImovelWeb
API, say) belongs beside it, not inside `olx_*`.

Sibling of `app/modules/meta_ads` — same persist-then-200-then-process
shape, for a sharper reason: OLX reads only our HTTP status code, retries
a non-2xx three times, and then discards the lead after 14 days with no
replay API.

Seam contract: `app/main.py` iterates `MODULES`, a list of zero-arg
callables each returning a `ModuleRegistration`.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Also calls `scheduler.configure()` to register the 15-minute inbox
    drain — same pattern as `meta_ads.register()`.
    """
    from app.main import ModuleRegistration
    from app.modules.portal_leads.routers import olx_webhook
    from app.modules.portal_leads.scheduler import configure as _configure_scheduler

    _configure_scheduler()

    return ModuleRegistration(routers=[olx_webhook.router], standard_routers=())


__all__ = ["register"]
