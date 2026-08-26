"""``portal_leads`` — inbound real-estate-portal lead ingestion.

**Two vendors, two pipes**, which is what the module was named for — the
category, not the vendor, so the second portal landed beside `olx_*` rather
than inside it:

* **Grupo OLX** (ZAP · VivaReal · OLX · ImovelWeb · Casa Mineira) — one
  webhook for all of them. Reads only our HTTP status code, retries a
  non-2xx three times, then discards the lead after 14 days with **no
  replay API**. The durable inbox row is the only safety net.

* **ImovelWeb / OpenNavent** (Navent · Grupo QuintoAndar) — a genuinely
  different vendor, despite the overlapping portal names. Allows **1.5
  seconds** to answer, retries for **72 hours**, and — decisively — exposes
  a **pull API**. So here reconciliation, not the webhook, is the
  durability guarantee, and that is what makes the tight budget survivable.

⚠️ An advertiser can be live on BOTH pipes at once: Grupo OLX ships its own
ImovelWeb bridge. The same enquiry then arrives twice under two vendor ids,
and `uq_sw_leads_org_external_lead` will not catch it because
`external_source` differs. Deliberately not solved with a fuzzy key —
surfacing a duplicate-SUSPECT count is advisory; merging is a human call.

Sibling of `app/modules/meta_ads` — same persist-then-answer-then-process
shape.

Seam contract: `app/main.py` iterates `MODULES`, a list of zero-arg
callables each returning a `ModuleRegistration`.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Also calls `scheduler.configure()`, which registers both inbox drains
    and the ImovelWeb reconciliation pull — same pattern as
    `meta_ads.register()`.
    """
    from app.main import ModuleRegistration
    from app.modules.portal_leads.routers import (
        imovelweb_webhook,
        olx_webhook,
        receiver_tokens,
    )
    from app.modules.portal_leads.scheduler import configure as _configure_scheduler

    _configure_scheduler()

    return ModuleRegistration(
        routers=[olx_webhook.router, imovelweb_webhook.router, receiver_tokens.router],
        standard_routers=(),
    )


__all__ = ["register"]
