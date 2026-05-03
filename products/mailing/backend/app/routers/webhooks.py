"""Resend webhook receiver — processes email events (Svix-protocol signature verified)."""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.database import get_admin_client
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


async def _resolve_resend_secret(request, body):
    """Per-request lookup of `RESEND_WEBHOOK_SECRET` so test-time monkeypatches
    on the settings module are honored (bypasses the import-time-capture trap)."""
    return ResolvedSecret(secret=settings.resend_webhook_secret or None)

# Map Resend event types to send_log status + timestamp field
EVENT_MAP = {
    "email.delivered": ("delivered", "delivered_at"),
    "email.opened": ("opened", "opened_at"),
    "email.clicked": ("clicked", "clicked_at"),
    "email.bounced": ("bounced", "bounced_at"),
    "email.complained": ("complained", None),
}


@router.post("/resend")
@limiter.limit(settings.webhook_rate_limit)
async def resend_webhook(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_resend_secret,
        scheme="svix",
        bypass_when_unset=True,
        log_prefix="resend-webhook",
    ),
):
    """Receive Resend webhook events and update send_logs accordingly.

    Auth: Svix-protocol HMAC signature on every payload, verified by the
    `webhook_endpoint(...)` dependency before any DB work. Resend signs
    `f"{svix-id}.{svix-timestamp}.{body}"` with the webhook secret
    (`RESEND_WEBHOOK_SECRET`). Mismatch → 401, no DB writes.

    Bypass: when `resend_webhook_secret` is unset (early-dev), the seed-lib
    helper accepts unsigned payloads with a WARNING. → KB §
    PATTERNS/webhook-signatures.md.
    """
    body = verified.body

    try:
        payload = json.loads(body) if body else {}
    except (ValueError, TypeError):
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
