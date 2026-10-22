"""Public click-tracking redirect — no auth; the signed token IS the credential.

``GET /api/email-marketing/t/c/{token}`` (P1b(c), 2026-10-10): verify the
``click`` token (``services/click_tracking``), record a ``link_clicks`` row, mark
the ``send_logs`` row clicked, then 302 to the URL INSIDE the token. The target
never comes from the request, and only http(s) targets verify, so this is not an
open redirect. Invalid / forged / other-purpose token → 400.

A click row stores NOTHING personal (owner decision 2026-10-11, LGPD): no IP,
no user agent — only which send (recipient) clicked which URL, and when.
Migration 248 dropped those columns.
"""
# NO `from __future__ import annotations` — slowapi's @limiter.limit resolves the
# endpoint signature at runtime (keeper `check_slowapi_with_pep563`).
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.dependencies import get_admin_client, get_settings
from app.modules.email_marketing.services.click_tracking import verify_token
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/email-marketing/t", tags=["Tracking"])

# A click never regresses a terminal / already-clicked delivery state.
_STATUS_KEPT = {"clicked", "bounced", "complained"}


@router.get("/c/{token}")
@limiter.limit(settings.webhook_rate_limit)
def click_redirect(request: Request, token: str, cfg=Depends(get_settings)):
    data = verify_token(cfg.jwt_secret, token)
    if not data:
        raise HTTPException(status_code=400, detail="Link inválido")

    db = get_admin_client()
    send_log_id, url = data["send_log_id"], data["url"]
    now = datetime.now(timezone.utc).isoformat()

    found = db.table("send_logs").select("id, status, clicked_at").eq("id", send_log_id).execute()
    if found.data:
        db.table("link_clicks").insert({
            "send_log_id": send_log_id,
            "url": url,
            "clicked_at": now,
        }).execute()
        log = found.data[0]
        update = {}
        if not log.get("clicked_at"):
            update["clicked_at"] = now
        if log.get("status") not in _STATUS_KEPT:
            update["status"] = "clicked"
        if update:
            db.table("send_logs").update(update).eq("id", send_log_id).execute()
    else:
        # The token is authentic (we signed it) but its send_log is gone
        # (deleted campaign/contact). Still take the reader where the link
        # promised; there is nothing to attribute the click to.
        logger.warning("click-tracking: send_log %s not found; redirecting without recording", send_log_id)

    return RedirectResponse(url, status_code=302)
