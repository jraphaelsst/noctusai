"""
WhatsApp Router — WhatsApp messaging integration endpoints.

Provides endpoints for sending messages, property cards, and viewing
message history through the Meta WhatsApp Business API or WAHA.

Supports two providers:
- **meta**: Meta WhatsApp Business API (Cloud API)
- **waha**: WAHA (WhatsApp HTTP API) — self-hosted alternative
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import success_response, paginated_response, calculate_pagination
from app.config import settings
from app.services.whatsapp_service import (
    WhatsAppConfig,
    send_message,
    send_property_card,
    get_message_history,
    get_whatsapp_config_from_env,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp"])


# ---------- Schemas ----------

class SendMessageRequest(BaseModel):
    phone: str = Field(..., min_length=8, max_length=20, description="Numero de telefone do destinatario")
    message: str = Field(..., min_length=1, max_length=4096, description="Conteudo da mensagem")
    cliente_id: Optional[str] = None


class SendPropertyRequest(BaseModel):
    phone: str = Field(..., min_length=8, max_length=20, description="Numero de telefone do destinatario")
    imovel_id: str = Field(..., description="ID do imovel a enviar")
    cliente_id: Optional[str] = None
    mensagem_adicional: Optional[str] = Field(
        default=None, max_length=1000,
        description="Mensagem adicional a incluir apos o cartao do imovel"
    )


# ---------- Helpers ----------

def _get_config_from_db(db) -> tuple:
    """
    Try to load WhatsApp config from the database (whatsapp_config table).
    Falls back to env vars if no DB config exists.
    Returns (WhatsAppConfig, provider_name).
    """
    try:
        result = db.table("whatsapp_config").select("*").eq("is_active", True).execute()
        if result.data:
            cfg = result.data[0]
            provider = cfg.get("provider", "meta")
            if provider == "waha":
                # WAHA provider — config stored in DB
                return WhatsAppConfig(
                    api_token=cfg.get("waha_api_key"),
                    phone_number_id=None,
                    api_version="waha",
                ), "waha"
            else:
                # Meta provider — use DB config if available, else env
                token = cfg.get("meta_api_token")
                phone_id = cfg.get("meta_phone_number_id")
                if token and phone_id:
                    return WhatsAppConfig(
                        api_token=token,
                        phone_number_id=phone_id,
                        api_version=cfg.get("meta_api_version", "v18.0"),
                    ), "meta"
    except Exception:
        pass
    # Fallback to env vars
    return get_whatsapp_config_from_env(), "meta"


# ---------- Endpoints ----------

@router.get("/config")
async def whatsapp_config_status(
    authorization: Optional[str] = Header(None),
):
    """
    Get WhatsApp integration configuration status.

    Returns whether the API is configured and operational,
    without exposing sensitive credentials.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    config, provider = _get_config_from_db(db)

    return success_response({
        "configured": config.is_configured,
        "provider": provider,
        "api_version": config.api_version,
        "phone_number_id_set": bool(config.phone_number_id),
        "api_token_set": bool(config.api_token),
        "dry_run": not config.is_configured,
    })


@router.post("/send")
async def enviar_mensagem(
    body: SendMessageRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Send a text message via WhatsApp.

    If the WhatsApp API is not configured, operates in dry-run mode
    and simulates message delivery (useful for development/testing).
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    config, provider = _get_config_from_db(db)

    # Send the message (WAHA uses different send path)
    if provider == "waha":
        result = await _send_via_waha(db, body.phone, body.message)
    else:
        result = await send_message(body.phone, body.message, config)

    # Store in message history
    try:
        msg_record = {
            "phone": result.get("phone", body.phone),
            "direction": "sent",
            "message": body.message,
            "message_type": "text",
            "status": result.get("status", "sent"),
            "metadata": {
                "message_id": result.get("message_id"),
                "dry_run": result.get("dry_run", False),
            },
        }
        if body.cliente_id:
            msg_record["cliente_id"] = body.cliente_id

        db.table("whatsapp_messages").insert(msg_record).execute()
    except Exception as e:
        logger.warning(f"Failed to store WhatsApp message record: {e}")

    log_action(
        user.id, "enviar", "whatsapp", None,
        f"Enviou mensagem WhatsApp para {body.phone}"
    )

    return success_response({
        "message_id": result.get("message_id"),
        "status": result.get("status"),
        "phone": result.get("phone"),
        "dry_run": result.get("dry_run", False),
    })


@router.post("/send-property")
async def enviar_imovel(
    body: SendPropertyRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Send a formatted property listing card via WhatsApp.

    Fetches the property details from the database and sends a formatted
    card with all relevant information to the specified phone number.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    config, provider = _get_config_from_db(db)

    # Fetch property data
    imovel_result = db.table("ativos").select("*").eq("id", body.imovel_id).single().execute()
    if not imovel_result.data:
        raise HTTPException(status_code=404, detail="Imovel nao encontrado")

    imovel_data = imovel_result.data

    # Send property card
    result = await send_property_card(body.phone, imovel_data, config)

    # Append additional message if provided
    if body.mensagem_adicional and result.get("status") == "sent":
        await send_message(body.phone, body.mensagem_adicional, config)

    # Store in message history
    try:
        formatted_message = result.get("formatted_message", "")
        msg_record = {
            "phone": result.get("phone", body.phone),
            "direction": "sent",
            "message": formatted_message,
            "message_type": "property_card",
            "status": result.get("status", "sent"),
            "metadata": {
                "message_id": result.get("message_id"),
                "imovel_id": body.imovel_id,
                "dry_run": result.get("dry_run", False),
            },
        }
        if body.cliente_id:
            msg_record["cliente_id"] = body.cliente_id

        db.table("whatsapp_messages").insert(msg_record).execute()
    except Exception as e:
        logger.warning(f"Failed to store WhatsApp message record: {e}")

    log_action(
        user.id, "enviar", "whatsapp", body.imovel_id,
        f"Enviou imovel {body.imovel_id} via WhatsApp para {body.phone}"
    )

    return success_response({
        "message_id": result.get("message_id"),
        "status": result.get("status"),
        "phone": result.get("phone"),
        "dry_run": result.get("dry_run", False),
        "formatted_message": result.get("formatted_message"),
    })


@router.get("/conversations")
async def listar_conversas(
    authorization: Optional[str] = Header(None),
):
    """
    List all conversations grouped by phone number.

    Returns a list of conversations with last message preview,
    timestamp, and unread count.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("whatsapp_messages").select("*").order(
        "created_at", desc=True
    ).execute()

    data = result.data or []

    # Group by phone
    grouped: dict = {}
    for msg in data:
        phone = msg.get("phone", "")
        if phone not in grouped:
            grouped[phone] = {
                "phone": phone,
                "last_message": msg.get("message") or msg.get("message_type", ""),
                "last_time": msg.get("created_at", ""),
                "unread": 0,
                "cliente_nome": None,
            }
        if msg.get("direction") == "received" and msg.get("status") != "read":
            grouped[phone]["unread"] += 1

    conversations = sorted(
        grouped.values(),
        key=lambda c: c.get("last_time", ""),
        reverse=True,
    )

    return success_response(conversations)


@router.get("/messages")
async def listar_mensagens(
    phone: str = Query(..., description="Phone number to fetch messages for"),
    authorization: Optional[str] = Header(None),
):
    """
    Retrieve all messages for a specific phone number, ordered chronologically.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("whatsapp_messages").select("*").eq(
        "phone", phone
    ).order("created_at", desc=False).execute()

    return success_response(result.data or [])


@router.get("/history/{phone}")
async def historico_mensagens(
    phone: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    authorization: Optional[str] = Header(None),
):
    """
    Retrieve message history for a specific phone number.

    Returns paginated message history ordered by most recent first.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    result = get_message_history(
        phone=phone,
        supabase=db,
        page=validated_page,
        page_size=validated_page_size,
    )

    return paginated_response(
        result["messages"],
        result["total"],
        validated_page,
        validated_page_size,
    )


# ---------- WAHA Provider Helpers ----------

async def _send_via_waha(db, phone: str, message: str) -> dict:
    """Send a message through the WAHA API."""
    config_result = db.table("whatsapp_config").select("*").eq("provider", "waha").eq("is_active", True).execute()
    if not config_result.data:
        return {"message_id": None, "status": "failed", "phone": phone, "error": "WAHA not configured"}

    cfg = config_result.data[0]
    waha_url = cfg.get("waha_api_url")
    waha_key = cfg.get("waha_api_key")
    session = cfg.get("waha_session_name", "default")

    if not waha_url:
        return {"message_id": f"dry_run_{phone}", "status": "sent", "phone": phone, "dry_run": True}

    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        if waha_key:
            headers["Authorization"] = f"Bearer {waha_key}"

        # Normalize phone for WAHA format
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) <= 11:
            digits = "55" + digits
        chat_id = f"{digits}@c.us"

        payload = {"chatId": chat_id, "text": message, "session": session}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{waha_url.rstrip('/')}/api/sendText",
                headers=headers,
                json=payload,
                timeout=30.0,
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "message_id": data.get("id", ""),
                    "status": "sent",
                    "phone": digits,
                }
            else:
                return {
                    "message_id": None,
                    "status": "failed",
                    "phone": digits,
                    "error": response.text,
                }
    except ImportError:
        return {"message_id": f"no_httpx_{phone}", "status": "sent", "phone": phone, "dry_run": True}
    except Exception as e:
        logger.error(f"WAHA send error: {e}")
        return {"message_id": None, "status": "failed", "phone": phone, "error": str(e)}
