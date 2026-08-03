"""Meta Lead-Ads -> unified-leads ingest — /api/leads/meta-ingest/*.

Single-lead ingest (``services.meta_ingest_service.ingest_meta_lead``) is
called directly (Python import, no HTTP hop) by the Meta Lead-Ads webhook
receiver — a peer module, not this router. This router exposes the ONE
thing that genuinely needs an explicit, human-triggered call: the bulk
backfill of ``meta_ads_leads`` rows synced before this mapping existed.
Mounted under ``/api/leads/meta-ingest`` — more specific than
``leads.router``'s catch-all ``/{lead_id}``, so (like ``sources``/
``corretores``/``import``) it MUST be registered before that router; see
``app/modules/leads/__init__.py::register()``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.leads.services import meta_ingest_service

router = APIRouter(prefix="/api/leads/meta-ingest", tags=["leads-meta-ingest"])


@router.post("/backfill", status_code=200)
def backfill_meta_ads_leads(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    result = meta_ingest_service.backfill_meta_ads_leads(client, org_id)
    return success_response(result)


__all__ = ["router"]
