"""
WhatsApp Service — Meta Business API integration for messaging.

Provides message sending capabilities via the Meta (WhatsApp) Business API.
Designed for graceful degradation: works in "dry run" mode when no API key
is configured, logging messages instead of sending them.

-- CREATE TABLE whatsapp_messages (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   cliente_id uuid,
--   phone text NOT NULL,
--   direction text NOT NULL CHECK (direction IN ('sent', 'received')),
--   message text NOT NULL,
--   message_type text NOT NULL DEFAULT 'text' CHECK (message_type IN ('text', 'property_card', 'image')),
--   metadata jsonb NOT NULL DEFAULT '{}',
--   status text NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'delivered', 'read', 'failed')),
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
import json
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WhatsAppConfig:
    """Configuration container for WhatsApp Business API."""

    def __init__(
        self,
        api_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: str = "v18.0",
    ):
        self.api_token = api_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{api_version}"

    @property
    def is_configured(self) -> bool:
        """Check if the API credentials are set."""
        return bool(self.api_token and self.phone_number_id)

    @property
    def send_url(self) -> str:
        """WhatsApp Cloud API message endpoint."""
        return f"{self.base_url}/{self.phone_number_id}/messages"

    @property
    def headers(self) -> Dict[str, str]:
        """HTTP headers for the API."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }


def _normalize_phone(phone: str) -> str:
    """
    Normalize a phone number to international format.

    Strips non-numeric characters and ensures country code is present.
    Defaults to Brazilian country code (55) if not provided.
    """
    digits = "".join(c for c in phone if c.isdigit())

    # If starts with 0, remove it
    if digits.startswith("0"):
        digits = digits[1:]

    # If doesn't start with country code, prepend Brazil's
    if len(digits) <= 11:
        digits = "55" + digits

    return digits


def _format_currency(value: float) -> str:
    """Format a number as Brazilian Real currency."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_property_message(imovel_data: Dict) -> str:
    """
    Build a formatted property card message for WhatsApp.

    Creates a readable text representation of a property listing.
    """
    lines = []

    # Title
    titulo = imovel_data.get("titulo_anuncio") or "Imovel Disponivel"
    lines.append(f"*{titulo}*")
    lines.append("")

    # Type and purpose
    tipo = imovel_data.get("tipo_imovel", "Imovel").capitalize()
    finalidade = imovel_data.get("finalidade", "venda").capitalize()
    lines.append(f"Tipo: {tipo} | {finalidade}")

    # Price
    valor = imovel_data.get("valor", 0)
    if valor:
        lines.append(f"Valor: {_format_currency(valor)}")

    # Location
    location_parts = []
    if imovel_data.get("bairro"):
        location_parts.append(imovel_data["bairro"])
    if imovel_data.get("cidade"):
        location_parts.append(imovel_data["cidade"])
    if imovel_data.get("estado"):
        location_parts.append(imovel_data["estado"])
    if location_parts:
        lines.append(f"Local: {', '.join(location_parts)}")

    if imovel_data.get("condominio_nome"):
        lines.append(f"Condominio: {imovel_data['condominio_nome']}")

    lines.append("")

    # Features
    features = []
    if imovel_data.get("quartos"):
        features.append(f"{imovel_data['quartos']} quartos")
    if imovel_data.get("suites"):
        features.append(f"{imovel_data['suites']} suites")
    if imovel_data.get("banheiros"):
        features.append(f"{imovel_data['banheiros']} banheiros")
    if imovel_data.get("vagas"):
        features.append(f"{imovel_data['vagas']} vagas")
    if features:
        lines.append(f"Caracteristicas: {' | '.join(features)}")

    # Area
    area = imovel_data.get("area_privativa") or imovel_data.get("area_total")
    if area:
        lines.append(f"Area: {area}m2")

    # IPTU
    if imovel_data.get("iptu"):
        lines.append(f"IPTU: {_format_currency(imovel_data['iptu'])}")

    # Description
    descricao = imovel_data.get("descricao_seo") or imovel_data.get("observacoes")
    if descricao:
        lines.append("")
        # Truncate long descriptions
        if len(descricao) > 300:
            descricao = descricao[:297] + "..."
        lines.append(descricao)

    # Virtual tour
    if imovel_data.get("tour_virtual_url"):
        lines.append("")
        lines.append(f"Tour virtual: {imovel_data['tour_virtual_url']}")

    return "\n".join(lines)


async def send_message(
    phone: str,
    message: str,
    config: WhatsAppConfig,
) -> Dict[str, Any]:
    """
    Send a text message via WhatsApp Business API.

    If the API is not configured, operates in dry-run mode and returns
    a simulated response. This allows development and testing without
    requiring an actual WhatsApp Business account.

    Args:
        phone: Recipient phone number (will be normalized)
        message: Text message content
        config: WhatsApp API configuration

    Returns:
        Dict with message_id, status, and phone
    """
    normalized_phone = _normalize_phone(phone)

    if not config.is_configured:
        logger.info(
            f"[WhatsApp DRY-RUN] Would send to {normalized_phone}: "
            f"{message[:100]}{'...' if len(message) > 100 else ''}"
        )
        return {
            "message_id": f"dry_run_{normalized_phone}",
            "status": "sent",
            "phone": normalized_phone,
            "dry_run": True,
        }

    # Real API call
    try:
        import httpx

        payload = {
            "messaging_product": "whatsapp",
            "to": normalized_phone,
            "type": "text",
            "text": {"body": message},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                config.send_url,
                headers=config.headers,
                json=payload,
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(
                    f"WhatsApp API error {response.status_code}: {response.text}"
                )
                return {
                    "message_id": None,
                    "status": "failed",
                    "phone": normalized_phone,
                    "error": response.text,
                }

            data = response.json()
            message_id = data.get("messages", [{}])[0].get("id", "unknown")

            return {
                "message_id": message_id,
                "status": "sent",
                "phone": normalized_phone,
            }

    except ImportError:
        logger.warning("httpx not installed. Running in dry-run mode.")
        return {
            "message_id": f"no_httpx_{normalized_phone}",
            "status": "sent",
            "phone": normalized_phone,
            "dry_run": True,
        }
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return {
            "message_id": None,
            "status": "failed",
            "phone": normalized_phone,
            "error": str(e),
        }


async def send_property_card(
    phone: str,
    imovel_data: Dict,
    config: WhatsAppConfig,
) -> Dict[str, Any]:
    """
    Send a formatted property listing card via WhatsApp.

    Formats the property data into a readable message and sends it.

    Args:
        phone: Recipient phone number
        imovel_data: Property data dict from the ativos table
        config: WhatsApp API configuration

    Returns:
        Dict with message_id, status, phone, and the formatted message
    """
    message = _build_property_message(imovel_data)
    result = await send_message(phone, message, config)
    result["formatted_message"] = message
    return result


def get_message_history(
    phone: str,
    supabase,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """
    Retrieve message history for a phone number.

    Args:
        phone: Phone number to look up
        supabase: Supabase client
        page: Page number
        page_size: Items per page

    Returns:
        Dict with messages list and total count
    """
    normalized = _normalize_phone(phone)

    # Count
    count_result = supabase.table("whatsapp_messages").select(
        "id", count="exact"
    ).eq("phone", normalized).execute()
    total = count_result.count if count_result.count is not None else 0

    # Data
    offset = (page - 1) * page_size
    result = supabase.table("whatsapp_messages").select("*").eq(
        "phone", normalized
    ).order("created_at", desc=True).range(
        offset, offset + page_size - 1
    ).execute()

    return {
        "messages": result.data or [],
        "total": total,
    }


async def send_via_waha(db, phone: str, message: str) -> dict:
    """Send a message through the WAHA API.

    Thin product wrapper around `noctusai_lib.integrations.whatsapp.WahaClient.send_text`
    (consumed via `get_whatsapp_client(...)` factory). Owns ERP-specific concerns:

    1. WAHA config lookup from the `whatsapp_config` table.
    2. Brazilian phone normalization (strip non-digits, prepend "55" country code
       when missing) — ERP keeps phone numbers in mixed formats from CRM imports.
    3. The legacy `{message_id, status, phone, [error|dry_run]}` envelope expected
       by the `/whatsapp/send` router.

    Transport (HTTP POST to `/api/sendText`, headers, response parsing) lives in
    the seed `WahaClient`; this function never touches `httpx` directly.
    """
    config_result = db.table("whatsapp_config").select("*").eq("provider", "waha").eq("is_active", True).execute()
    if not config_result.data:
        return {"message_id": None, "status": "failed", "phone": phone, "error": "WAHA not configured"}

    cfg = config_result.data[0]
    waha_url = cfg.get("waha_api_url")
    waha_key = cfg.get("waha_api_key")
    session = cfg.get("waha_session_name", "default")

    if not waha_url:
        return {"message_id": f"dry_run_{phone}", "status": "sent", "phone": phone, "dry_run": True}

    # Normalize phone for WAHA format (ERP-specific: CRM imports may omit country code).
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) <= 11:
        digits = "55" + digits
    chat_id = f"{digits}@c.us"

    from noctusai_lib.integrations.whatsapp import get_whatsapp_client

    client = get_whatsapp_client(base_url=waha_url, api_key=waha_key, session=session)
    try:
        data = await client.send_text(chat_id, message)
    except Exception as e:
        # WahaClient raises httpx.HTTPStatusError on non-2xx (raise_for_status).
        # Surface the legacy error envelope so router-side dry-run + history-write
        # paths keep working.
        logger.error("WAHA send error: %s", e)
        return {"message_id": None, "status": "failed", "phone": digits, "error": str(e)}
    return {
        "message_id": data.get("id", ""),
        "status": "sent",
        "phone": digits,
    }


def get_whatsapp_config_from_env() -> WhatsAppConfig:
    """
    Load WhatsApp configuration from environment variables.

    Returns:
        WhatsAppConfig instance (may be unconfigured if env vars are missing)
    """
    import os

    return WhatsAppConfig(
        api_token=os.environ.get("WHATSAPP_API_TOKEN"),
        phone_number_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID"),
        api_version=os.environ.get("WHATSAPP_API_VERSION", "v18.0"),
    )
