"""Resend webhook receiver — processes email events (Svix-protocol signature verified)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException

from noctusai_lib.security.webhook_signatures import verify_svix_signature

from app.config import settings
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

    Auth: Svix-protocol HMAC signature on every payload, verified before
    any DB work. Resend signs `f"{svix-id}.{svix-timestamp}.{body}"` with
    the webhook secret (configured per-endpoint in the Resend dashboard,
    stored as `RESEND_WEBHOOK_SECRET`). Mismatch → 401, no DB writes.

    Bypass: when `resend_webhook_secret` is unset (early-dev), accept
    unsigned payloads with a WARNING. Same convention as every other
    webhook on the platform — see KNOWLEDGE-BASE/CONTEXT/PATTERNS/webhooks.md.
    """
    body = await request.body()

    secret = settings.resend_webhook_secret
    if secret:
        svix_id = request.headers.get("svix-id", "")
        svix_timestamp = request.headers.get("svix-timestamp", "")
        signature_header = request.headers.get("svix-signature", "")
        if not verify_svix_signature(
            svix_id=svix_id,
            svix_timestamp=svix_timestamp,
            body=body,
            signature_header=signature_header,
            secret=secret,
        ):
            logger.warning(
                "Resend webhook rejected: signature mismatch (svix_id=%s)",
                svix_id or "<missing>",
            )
            raise HTTPException(status_code=401, detail="invalid webhook signature")
    else:
        logger.warning(
            "RESEND_WEBHOOK_SECRET unset — accepting Resend webhook without verification. "
            "Set it in any environment receiving real Resend traffic."
        )

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
