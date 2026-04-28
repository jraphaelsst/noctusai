"""
Core C2 — weekly audit-log digest router (ai-expansion Phase 9).

Two endpoints:
  - POST /api/admin/audit-digest/{org_id}      — build + send to org admins
  - GET  /api/admin/audit-digest/{org_id}/preview — build + return body without sending

Both gated behind `get_current_admin` (platform admin role). Cron callers
pass a service-role token via the same auth header — Supabase auth still
resolves to a user record, so we treat cron jobs as a special platform
admin in `noctus_users`.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from noctusai_lib.ai import consent_required

from app.database import get_admin_client
from app.dependencies import get_current_admin
from app.services import audit_digest_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Audit Digest"])


@router.post("/api/admin/audit-digest/{org_id}")
async def send_audit_digest_endpoint(
    org_id: str,
    period_days: int = 7,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("core.audit_digest")),
):
    """Build the weekly audit-log narrative digest and send to org admins."""
    await get_current_admin(authorization)
    db = get_admin_client()
    try:
        result = await audit_digest_service.send_weekly_audit_digest(
            db, org_id=org_id, period_days=period_days
        )
    except Exception as e:
        logger.error("audit_digest send failed for org=%s: %s", org_id, e)
        raise HTTPException(status_code=500, detail="Erro ao gerar digest de auditoria")
    if result.get("error") == "org_not_found":
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    return {"data": result}


@router.get("/api/admin/audit-digest/{org_id}/preview")
async def preview_audit_digest_endpoint(
    org_id: str,
    period_days: int = 7,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("core.audit_digest")),
):
    """Build the digest and return its rendered html/text without sending —
    useful for dashboards + cron debugging."""
    await get_current_admin(authorization)
    db = get_admin_client()
    built = await audit_digest_service.build_digest(
        db, org_id=org_id, period_days=period_days
    )
    if built is None:
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    digest, recipients, summary = built
    return {
        "data": {
            "subject": digest.subject,
            "text": digest.text,
            "html": digest.html,
            "recipients": [r.get("email") for r in recipients if r.get("email")],
            "summary": summary,
        }
    }
