"""Resend webhook receiver — processes email events (no auth, signature verified)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from app.database import get_admin_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

# Map Resend event types to send_log status + timestamp field
EVENT_MAP = {
    "email.delivered": ("delivered", "delivered_at"),
    "email.opened": ("opened", "opened_at"),
    "email.clicked": ("clicked", "clicked_at"),
    "email.bounced": ("bounced", "bounced_at"),
    "email.complained": ("complained", None),
}


@router.post("/resend")
async def resend_webhook(request: Request):
    """Receive Resend webhook events and update send_logs accordingly.

    No auth — Resend calls this endpoint directly.
    TODO: verify webhook signature with svix/HMAC.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type")
    data = payload.get("data", {})
    message_id = data.get("email_id") or data.get("message_id")

    if not event_type or not message_id:
        return {"ok": True, "skipped": True}

    mapping = EVENT_MAP.get(event_type)
    if not mapping:
        logger.debug("Ignoring Resend event: %s", event_type)
        return {"ok": True, "skipped": True}

    status, ts_field = mapping
    now = datetime.now(timezone.utc).isoformat()
    db = get_admin_client()

    # Find send_log by resend_message_id
    result = (db.table("send_logs").select("id, contact_id, org_id")
              .eq("resend_message_id", message_id).execute())

    if not result.data:
        logger.warning("Webhook: no send_log for message_id %s", message_id)
        return {"ok": True, "not_found": True}

    log = result.data[0]
    update = {"status": status}
    if ts_field:
        update[ts_field] = now

    db.table("send_logs").update(update).eq("id", log["id"]).execute()

    # On bounce/complaint: mark contact as bounced/complained
    if status in ("bounced", "complained"):
        db.table("contacts").update({
            "status": status,
            "updated_at": now,
        }).eq("id", log["contact_id"]).execute()

        # Create unsubscribe audit record for complaints
        if status == "complained":
            db.table("unsubscribes").insert({
                "org_id": log["org_id"],
                "contact_id": log["contact_id"],
                "email": data.get("to", [""])[0] if isinstance(data.get("to"), list) else "",
                "reason": "complaint",
            }).execute()

    logger.info("Webhook processed: %s for message %s", event_type, message_id)
    return {"ok": True}
