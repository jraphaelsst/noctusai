"""
WAHA WhatsApp Webhook Receiver — handles inbound events from WAHA.

Receives webhook events for message delivery, read receipts, and incoming
messages. Routes events to the appropriate handler based on event type.

Table: erp.whatsapp_messages (updates status on delivery/read)
Table: erp.whatsapp_config (reads provider config)
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, get_admin_client
from app.responses import success_response
from app.webhook_utils import verify_hmac_sha256

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp-webhook"])


# ── Schemas ──────────────────────────────────────────────────────────

class WAHAMessageEvent(BaseModel):
    event: str = Field(..., description="Event type: message, message.ack, etc.")
    session: str = Field(default="default")
    payload: dict = Field(default_factory=dict)


class WAHASessionRequest(BaseModel):
    session_name: str = Field(default="default", max_length=100)


# ── Webhook Endpoint (unauthenticated — called by WAHA server) ──────

@router.post("/webhook")
async def waha_webhook(event: WAHAMessageEvent, request: Request, x_hub_signature: Optional[str] = Header(None)):
    """
    Receive webhook events from WAHA.

    WAHA sends events for:
    - message: new incoming message
    - message.ack: delivery/read status update
    - session.status: session connection status changes
    """
    logger.info(f"WAHA webhook event: {event.event} session={event.session}")

    admin = get_admin_client()
    if not admin:
        raise HTTPException(status_code=503, detail="Serviço indisponível")

    # Find org by WAHA session
    config_result = (
        admin.table("whatsapp_config")
        .select("org_id, webhook_secret")
        .eq("waha_session_name", event.session)
        .eq("provider", "waha")
        .eq("is_active", True)
        .execute()
    )
    if not config_result.data:
        logger.warning(f"No config found for WAHA session: {event.session}")
        return {"status": "ignored", "reason": "session_not_configured"}

    config_row = config_result.data[0]
    org_id = config_row["org_id"]

    # Verify HMAC signature when webhook_secret is configured
    webhook_secret = config_row.get("webhook_secret")
    if webhook_secret:
        body_bytes = await request.body()
        if not x_hub_signature or not verify_hmac_sha256(body_bytes, x_hub_signature, webhook_secret):
            raise HTTPException(status_code=401, detail="Assinatura do webhook inválida")

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
