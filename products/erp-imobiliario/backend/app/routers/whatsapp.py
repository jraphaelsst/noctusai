"""
WhatsApp Router — WhatsApp messaging integration endpoints.

Provides endpoints for sending messages, property cards, and viewing
message history through the Meta WhatsApp Business API.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import success_response, paginated_response, calculate_pagination
from app.config import settings
from app.services.whatsapp_service import (
    send_message,
    send_property_card,
    get_message_history,
    get_whatsapp_config_from_env,
    WhatsAppConfig,
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
    config = get_whatsapp_config_from_env()

    return success_response({
        "configured": config.is_configured,
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
    config = get_whatsapp_config_from_env()

    # Send the message
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
    config = get_whatsapp_config_from_env()

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
