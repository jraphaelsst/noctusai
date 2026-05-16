"""Public unsubscribe endpoints — no auth required, HMAC token verification."""
import hashlib
import hmac
import base64
import logging

from fastapi import APIRouter, HTTPException
from app.dependencies import get_admin_client
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/email-marketing/unsubscribe', tags=["Unsubscribe"])


def generate_token(org_id: str, contact_id: str, email: str) -> str:
    """Generate HMAC-signed unsubscribe token."""
    payload = f"{org_id}:{contact_id}:{email}"
    sig = hmac.new(settings.jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def verify_token(token: str) -> dict:
    """Verify and decode an unsubscribe token."""
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
        # Token verification can fail for many reasons (malformed base64,
        # bad signature, payload missing fields). Caller treats None as
        # "invalid token" and returns 400 — but we log so spikes in failures
        # signal either a token-format change or an attacker probing.
        logger.warning("unsubscribe: token verification failed (%s); rejecting", exc)
        return None


@router.get("/{token}")
async def unsubscribe_page(token: str):
    """Render unsubscribe confirmation — returns token info for frontend to display."""
    data = verify_token(token)
    if not data:
        raise HTTPException(status_code=400, detail="Link de descadastro invalido")
    return {"email": data["email"], "valid": True}


@router.post("/{token}")
async def process_unsubscribe(token: str):
    """Process the unsubscribe — mark contact as unsubscribed, create audit record."""
    data = verify_token(token)
    if not data:
        raise HTTPException(status_code=400, detail="Link de descadastro invalido")

    db = get_admin_client()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

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
    return {"ok": True, "message": "Descadastro realizado com sucesso"}
