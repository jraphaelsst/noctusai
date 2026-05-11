"""
POST /api/metas/digest/{periodo_id} — send the biweekly closing digest email.

Admin-only (enforced via RLS on the downstream tables; this router simply
requires an authenticated session and lets the `db.get_user_client()` raise
403 if the caller lacks permission).

The `recipient` query param defaults to the org owner's email (looked up via
`auth.users` through the service-role client). Callers — typically an n8n cron
on Friday of each quinzena — pass `recipient=owner@agency.com` explicitly.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query

from app.dependencies import get_current_user
from app.database import db as db_mod
from app.services import meta_rankings_service
from app.services.metas_digest_service import send_biweekly_digest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metas/digest", tags=["Metas · Digest"])


@router.post("/{periodo_id}")
async def enviar_digest(
    periodo_id: str,
    recipient: str = Query(..., description="Email address to deliver the digest to"),
    auth = Depends(get_current_user)):
    """Send the biweekly digest for a period to `recipient`.

    Admin-only. The underlying tables have RLS + `has_role` checks but we
    also gate here because the admin client bypasses RLS.
    """
    user, _ = auth
    role = (user.user_metadata or {}).get("erp_role") or (user.user_metadata or {}).get("noctus_role")
    if role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Admin privileges required")

    admin_db = db_mod.get_admin_client()
    periodo_res = (
        admin_db.table("meta_periodos").select("*").eq("id", periodo_id).execute()
    )
    periodo = (periodo_res.data or [None])[0]
    if not periodo:
        raise HTTPException(status_code=404, detail="Período não encontrado")

    rankings = meta_rankings_service.compute_rankings(
        admin_db,
        org_id=periodo["org_id"],
        data_inicio=periodo["data_inicio"],
        data_fim=periodo["data_fim"],
    )

    result = await send_biweekly_digest(
        db=admin_db,
        periodo_id=periodo_id,
        recipient=recipient,
        top_rankings=rankings.get("unificado", []),
    )
    return result
