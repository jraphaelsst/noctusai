"""WAHA payload parsing helpers.

Ported verbatim from `whatsapp-google-scheduling/app/services/waha/mappers.py`
2026-05-03. Pure functions — no Redis / DB / network. Future non-WAHA
providers (Twilio, Cloud API) get sibling parser modules; the InboundMessage
output shape stays uniform.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from noctusai_lib.integrations.whatsapp.types import (
    WhatsAppIgnoredEvent,
    WhatsAppInboundMessage,
    WhatsAppMedia,
    WhatsAppPayloadError,
)


def parse_waha_inbound_message(payload: dict[str, Any]) -> WhatsAppInboundMessage:
    """Parse a WAHA webhook payload into an `WhatsAppInboundMessage`.

    Raises:
        WhatsAppIgnoredEvent: event type is structurally valid but should be
            silently dropped (e.g. `session.status`, own-message echoes).
        WhatsAppPayloadError: payload is missing chat_id or has neither text
            nor media.
    """
    event = payload.get("event")
    if event and event not in {"message", "message.any"}:
        raise WhatsAppIgnoredEvent(f"Ignoring unsupported WAHA event: {event}")

    event_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    if event == "message.any" and is_own_or_api_message(event_payload):
        raise WhatsAppIgnoredEvent("Ignoring own/API message.any event")

    chat_id = first_text(event_payload, "chatId", "from", "fromNumber")
    text = first_text(event_payload, "body", "text", "message")
    provider_message_id = extract_message_id(event_payload)
    session = str(payload.get("session") or event_payload.get("session") or "default")
    media = extract_media(event_payload)
    from_name = extract_from_name(event_payload)

    if not chat_id:
        raise WhatsAppPayloadError("WAHA webhook payload is missing chat id")
    if not text and not media:
        raise WhatsAppPayloadError("WAHA webhook payload has no text and no media")

    return WhatsAppInboundMessage(
        provider_message_id=provider_message_id,
        chat_id=chat_id,
        from_phone=phone_from_chat_id(chat_id),
        text=text,
        session=session,
        media=media,
        from_name=from_name,
    )


def build_send_text_body(session: str, chat_id: str, text: str) -> dict[str, Any]:
    """Build the WAHA `/api/sendText` request body."""
    return {"session": session, "chatId": chat_id, "text": text}


def chat_id_for_phone(phone: str) -> str:
    """Convert an E.164-style phone (`+5511999...`) to a WAHA `chatId`
    (`5511999...@c.us`)."""
    digits = phone.lstrip("+")
    return f"{digits}@c.us"


def phone_from_chat_id(chat_id: str) -> str:
    """Inverse of `chat_id_for_phone`."""
    phone = chat_id.split("@", 1)[0]
    return f"+{phone}" if phone and not phone.startswith("+") else phone


def rewrite_vendor_media_url(
    url: str,
    *,
    external_base_url: str,
    internal_base_url: str,
) -> str:
    """Rewrite a WAHA-emitted media URL from its external host to the
    docker-internal host.

    Production bug (SESSION-NOTES §4.3, workspace commit ``fedd4cf``):
    WAHA emits media URLs against its OWN external-facing hostname
    (e.g. ``http://localhost:3000/api/files/...``) because WAHA assumes
    the consumer is the operator's browser. From inside the ``app``
    container ``localhost:3000`` IS the app — the TCP connection fails.

    WAHA media-URL response shape (validated live; reproduced here
    because the workspace ``backend/WAHA_RESPONSE_FORMATS.md`` is NOT
    in-home — Wave 2 product-port MUST carry that file):

        payload.media.url == "<WAHA_EXTERNAL_BASE>/api/files/<session>/<id>.<ext>"
        # e.g. "http://localhost:3000/api/files/default/false_..._3EB0.oga"

    Rule: when ``url``'s scheme+host+port matches ``external_base_url``,
    swap them for ``internal_base_url``'s (path/query/fragment kept
    verbatim). External CDN URLs (anything NOT matching the external
    base authority) pass through UNCHANGED — same shape applies to any
    vendor emitting self-referential URLs (Supabase storage, MinIO).

    No-ops safely (returns ``url`` unchanged) when either base is empty
    or ``url`` is not absolute.
    """
    if not url or not external_base_url or not internal_base_url:
        return url

    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return url  # relative URL — nothing to rewrite.

    ext = urlsplit(external_base_url)
    if parsed.netloc != ext.netloc:
        return url  # external CDN / other host — pass through unchanged.

    internal = urlsplit(internal_base_url)
    return urlunsplit(
        (
            internal.scheme or parsed.scheme,
            internal.netloc or parsed.netloc,
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_message_id(payload: dict[str, Any]) -> str | None:
    message_id = payload.get("id")
    if isinstance(message_id, str):
        return message_id
    if isinstance(message_id, dict):
        serialized = message_id.get("_serialized") or message_id.get("id")
        if isinstance(serialized, str):
            return serialized
    return None


def extract_media(payload: dict[str, Any]) -> WhatsAppMedia | None:
    if not payload.get("hasMedia"):
        return None
    media = payload.get("media")
    if not isinstance(media, dict):
        return None
    url = media.get("url") if isinstance(media.get("url"), str) else None
    mimetype = media.get("mimetype") if isinstance(media.get("mimetype"), str) else None
    if not url and not mimetype:
        return None
    return WhatsAppMedia(url=url, mimetype=mimetype)


def is_own_or_api_message(payload: dict[str, Any]) -> bool:
    if payload.get("fromMe") is True:
        return True
    return payload.get("source") == "api"


def extract_from_name(payload: dict[str, Any]) -> str | None:
    direct = first_text(payload, "notifyName", "pushName")
    if direct:
        return direct
    data = payload.get("_data")
    if isinstance(data, dict):
        nested = first_text(data, "notifyName", "pushName")
        if nested:
            return nested
    return None
