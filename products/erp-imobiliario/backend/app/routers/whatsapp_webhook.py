"""
WAHA WhatsApp Webhook Receiver — handles inbound events from WAHA.

Receives webhook events for message delivery, read receipts, and incoming
messages. Routes events to the appropriate handler based on event type.

Table: erp.whatsapp_messages (updates status on delivery/read)
Table: erp.whatsapp_config (reads provider config)
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.dependencies import get_current_user, get_user_client, get_admin_client
from app.rate_limit import limiter
from app.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp-webhook"])


async def _resolve_waha_secret(request: Request, body: bytes) -> ResolvedSecret:
    """Look up the WAHA per-session webhook secret from `whatsapp_config`.

    The session name comes from the (unverified) request body. The resolver
    parses the body once to find the session, fetches the row, and stashes
    `(org_id, session_name)` on `extras` so the handler doesn't repeat the
    lookup. If the session isn't configured, returns a `None` secret —
    paired with `bypass_when_unset=True`, that preserves the legacy
    behavior of letting unconfigured sessions through (security gap
    tracked as a follow-up).
    """
    try:
        payload = json.loads(body) if body else {}
    except (ValueError, TypeError):
        return ResolvedSecret(secret=None, extras=None)

    session_name = payload.get("session") or "default"
    admin = get_admin_client()
    if not admin:
        return ResolvedSecret(secret=None, extras=None)
    res = (
        admin.table("whatsapp_config")
        .select("org_id, webhook_secret")
        .eq("waha_session_name", session_name)
        .eq("provider", "waha")
        .eq("is_active", True)
        .execute()
    )
    if not res.data:
        return ResolvedSecret(secret=None, extras={"session_name": session_name, "org_id": None})
    row = res.data[0]
    return ResolvedSecret(
        secret=row.get("webhook_secret") or None,
        extras={"session_name": session_name, "org_id": row["org_id"]},
    )


# ── Schemas ──────────────────────────────────────────────────────────

class WAHAMessageEvent(BaseModel):
    event: str = Field(..., description="Event type: message, message.ack, etc.")
    session: str = Field(default="default")
    payload: dict = Field(default_factory=dict)


class WAHASessionRequest(BaseModel):
    session_name: str = Field(default="default", max_length=100)


# ── Webhook Endpoint (unauthenticated — called by WAHA server) ──────

@router.post("/webhook")
@limiter.limit(settings.webhook_rate_limit)
async def waha_webhook(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_waha_secret,
        scheme="sha256_prefixed",
        signature_header="X-Hub-Signature",
        bypass_when_unset=True,
        log_prefix="waha-webhook",
    ),
):
    """
    Receive webhook events from WAHA.

    WAHA sends events for:
    - message: new incoming message
    - message.ack: delivery/read status update
    - session.status: session connection status changes
    """
    try:
        payload_dict = json.loads(verified.body) if verified.body else {}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = WAHAMessageEvent.model_validate(payload_dict)
    logger.info(f"WAHA webhook event: {event.event} session={event.session}")

    admin = get_admin_client()
    if not admin:
        raise HTTPException(status_code=503, detail="Serviço indisponível")

    org_id = (verified.extras or {}).get("org_id")
    if not org_id:
        logger.warning(f"No config found for WAHA session: {event.session}")
        return {"status": "ignored", "reason": "session_not_configured"}

    if event.event == "message":
        return await _handle_incoming_message(admin, org_id, event.payload)
    elif event.event == "message.ack":
        return await _handle_ack(admin, org_id, event.payload)
    elif event.event == "session.status":
        logger.info(f"Session status change: {event.payload}")
        return {"status": "ok"}
    else:
        return {"status": "ignored", "reason": f"unhandled_event:{event.event}"}


async def _handle_incoming_message(admin, org_id: str, payload: dict) -> dict:
    """Store an incoming message from WAHA."""
    body = payload.get("body", "")
    from_phone = payload.get("from", "").replace("@c.us", "")
    msg_id = payload.get("id", "")

    if not from_phone or not body:
        return {"status": "ignored", "reason": "empty_message"}

    # Try to link to existing client by phone
    client_result = (
        admin.table("clientes")
        .select("id")
        .eq("org_id", org_id)
        .ilike("telefone", f"%{from_phone[-8:]}%")
        .limit(1)
        .execute()
    )
    cliente_id = client_result.data[0]["id"] if client_result.data else None

    msg_data = {
        "org_id": org_id,
        "phone": from_phone,
        "direction": "received",
        "message": body,
        "message_type": "text",
        "metadata": {"waha_id": msg_id, "raw": payload},
        "status": "delivered",
        "cliente_id": cliente_id,
    }
    admin.table("whatsapp_messages").insert(msg_data).execute()

    return {"status": "ok", "stored": True}


async def _handle_ack(admin, org_id: str, payload: dict) -> dict:
    """Update message status based on delivery acknowledgment."""
    ack = payload.get("ack")
    msg_id = payload.get("id", {}).get("id", "")

    if not msg_id:
        return {"status": "ignored"}

    # Map WAHA ack levels to our status
    status_map = {1: "sent", 2: "delivered", 3: "read"}
    new_status = status_map.get(ack)
    if not new_status:
        return {"status": "ignored", "reason": f"unknown_ack:{ack}"}

    admin.table("whatsapp_messages").update(
        {"status": new_status}
    ).eq("org_id", org_id).contains(
        "metadata", {"waha_id": msg_id}
    ).execute()

    return {"status": "ok", "updated_status": new_status}


# ── WAHA Session Management (authenticated) ─────────────────────────

@router.get("/sessions")
async def listar_sessions(authorization: Optional[str] = Header(None)):
    """List WAHA sessions for the org."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    result = (
        sb.table("whatsapp_config")
        .select("*")
        .eq("provider", "waha")
        .execute()
    )

    return success_response(result.data or [])


@router.post("/sessions/start")
async def iniciar_session(
    body: WAHASessionRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Start a WAHA session (sends request to WAHA API).
    Requires WAHA config to be set up for the org.
    """
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    config_result = (
        sb.table("whatsapp_config")
        .select("*")
        .eq("provider", "waha")
        .single()
        .execute()
    )
    if not config_result.data:
        raise HTTPException(
            status_code=400,
            detail="Configuração WAHA não encontrada. Configure em Configurações > WhatsApp.",
        )

    config = config_result.data
    waha_url = config.get("waha_api_url")
    waha_key = config.get("waha_api_key")

    if not waha_url:
        raise HTTPException(status_code=400, detail="URL da API WAHA não configurada")

    # Call WAHA API to start session
    try:
        import httpx

        headers = {}
        if waha_key:
            headers["Authorization"] = f"Bearer {waha_key}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{waha_url.rstrip('/')}/api/sessions/{body.session_name}/start",
                headers=headers,
                timeout=30.0,
            )
            return success_response({
                "session": response.json() if response.status_code == 200 else None,
                "waha_status": response.status_code,
            })
    except ImportError as exc:
        logger.warning("whatsapp_webhook: httpx unavailable (%s); returning dry_run for WAHA session start", exc)
        return success_response({
            "session": {"session": body.session_name, "status": "dry_run"},
            "waha_status": None,
        })
    except Exception as e:
        logger.error(f"WAHA session start error: {e}")
        raise HTTPException(status_code=502, detail=f"Erro ao conectar WAHA: {str(e)}")
