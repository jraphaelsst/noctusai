"""Public unsubscribe endpoints — no auth required, HMAC token verification."""
import hashlib
import hmac
import base64
import logging

from fastapi import APIRouter, HTTPException
from app.dependencies import get_admin_client
from app.config import settings
from noctusai_lib.security import signed_tokens
from app.modules.email_marketing.services.unsubscribe_links import TOKEN_PURPOSE, make_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/email-marketing/unsubscribe', tags=["Unsubscribe"])


def generate_token(org_id: str, contact_id: str, email: str) -> str:
    """Signed unsubscribe token for this app's secret (``unsubscribe_links.make_token``)."""
    return make_token(settings.jwt_secret, org_id, contact_id, email)


def _verify_legacy_token(token: str) -> dict | None:
    """The pre-2026-10-10 hand-rolled format (base64 of ``org:contact:email:sig16``).
    Links already in sent emails must keep working; never minted again."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.rsplit(":", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        expected = hmac.new(settings.jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        org_id, contact_id, email = payload.split(":", 2)
        return {"org_id": org_id, "contact_id": contact_id, "email": email}
    except Exception as exc:
        # Caller treats None as "invalid token" and returns 400; logged so a
        # spike signals a format change or an attacker probing.
        logger.warning("unsubscribe: legacy token verification failed (%s); rejecting", exc)
        return None


def verify_token(token: str) -> dict | None:
    """Payload of a valid unsubscribe token, else None (signed format first,
    then the legacy format)."""
    data = signed_tokens.verify(TOKEN_PURPOSE, token, settings.jwt_secret)
    if data and all(data.get(k) for k in ("org_id", "contact_id", "email")):
        return data
    return _verify_legacy_token(token)


@router.get("/{token}")
async def unsubscribe_page(token: str):
    """Render unsubscribe confirmation — returns token info for frontend to display."""
    data = verify_token(token)
    if not data:
        raise HTTPException(status_code=400, detail="Link de descadastro invalido")
    return {"email": data["email"], "valid": True}


@router.post("/{token}")
async def process_unsubscribe(token: str):
    """Process the unsubscribe — mark contact as unsubscribed, create audit record.

    Also the RFC 8058 one-click target: mail clients POST
    ``List-Unsubscribe=One-Click`` (form body, ignored) to the List-Unsubscribe
    URL with no page interaction."""
    data = verify_token(token)
    if not data:
        raise HTTPException(status_code=400, detail="Link de descadastro invalido")

    db = get_admin_client()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    current = (db.table("contacts").select("status")
               .eq("id", data["contact_id"]).eq("org_id", data["org_id"]).execute())
    if current.data and current.data[0].get("status") == "unsubscribed":
        # Idempotent: mail clients replay one-click POSTs (RFC 8058).
        return {"ok": True, "already": True, "email": data["email"]}

    # Update contact status
    db.table("contacts").update({
        "status": "unsubscribed",
        "unsubscribed_at": now,
        "updated_at": now,
    }).eq("id", data["contact_id"]).eq("org_id", data["org_id"]).execute()

    # Create audit record
    db.table("unsubscribes").insert({
        "org_id": data["org_id"],
        "contact_id": data["contact_id"],
        "email": data["email"],
        "reason": "link_click",
    }).execute()

    logger.info("Unsubscribe processed: %s (org=%s)", data["email"], data["org_id"])
    return {"ok": True, "email": data["email"], "message": "Descadastro realizado com sucesso"}
