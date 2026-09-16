"""WAHA payload parsing helpers.

Ported verbatim from `whatsapp-google-scheduling/app/services/waha/mappers.py`
2026-05-03. Pure functions — no Redis / DB / network. Future non-WAHA
providers (Twilio, Cloud API) get sibling parser modules; the InboundMessage
output shape stays uniform.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from noctusai_lib.integrations.whatsapp.types import (
    GroupInfo,
    GroupParticipant,
    ParticipantChangeResult,
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
    group_id = group_id_from_chat_id(chat_id)
    author_id = extract_author_id(event_payload)

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
        group_id=group_id,
        author_id=author_id,
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


# ---- Group support -----------------------------------------------------


def group_id_from_chat_id(chat_id: str) -> str | None:
    """A WAHA `chatId` ending `@g.us` identifies a group chat; return it
    as `group_id` when so, else `None` for a 1:1 chat. Additive sibling
    of `phone_from_chat_id` — does not change `from_phone`'s existing
    (group-misattributing) behavior, see `WhatsAppInboundMessage`."""
    return chat_id if chat_id.endswith("@g.us") else None


def extract_author_id(payload: dict[str, Any]) -> str | None:
    """The sending participant's JID within a group message. WAHA/NOWEB
    emits this as `participant` (canonical field on a group `message`
    event); some payload shapes carry it as `author` instead. Absent
    (and correctly `None`) on a 1:1 chat payload, which carries neither
    field."""
    return first_text(payload, "participant", "author") or None


def normalize_waha_id(value: Any) -> str | None:
    """WAHA emits identifiers — message ids, and (per the Groups API)
    sometimes group/participant ids too — either as a bare string or as
    `{"_serialized": "...", "id": "..."}`. Normalizes both shapes to the
    plain string form. Sibling of `extract_message_id`, generalized for
    the group-parsing call sites (left `extract_message_id` itself
    untouched to avoid touching an already-covered code path)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        serialized = value.get("_serialized") or value.get("id")
        if isinstance(serialized, str):
            return serialized
    return None


def group_participant_from_waha(item: dict[str, Any]) -> GroupParticipant:
    """Parse one WAHA group-participant entry into a `GroupParticipant`.

    WAHA's participant schema carries `id` (string or `{"_serialized":
    ...}`) plus `isAdmin` / `isSuperAdmin` booleans — collapsed here into
    the single `role` field so callers get one Literal instead of two
    separate flags to check.
    """
    participant_id = normalize_waha_id(item.get("id")) or ""
    role: Literal["participant", "admin", "superadmin"]
    if item.get("isSuperAdmin"):
        role = "superadmin"
    elif item.get("isAdmin"):
        role = "admin"
    else:
        role = "participant"
    return GroupParticipant(id=participant_id, role=role)


def group_info_from_waha(body: dict[str, Any]) -> GroupInfo:
    """Parse a WAHA group object (`POST/GET .../groups[/id]`) into a
    `GroupInfo`. `participants` may be absent on the list-groups summary
    shape — defaults to `[]`; call `list_participants` for the
    authoritative roster."""
    group_id = normalize_waha_id(body.get("id")) or ""
    name = body.get("name") or body.get("subject") or ""
    raw_participants = body.get("participants")
    participants = (
        [group_participant_from_waha(p) for p in raw_participants if isinstance(p, dict)]
        if isinstance(raw_participants, list)
        else []
    )
    owner = normalize_waha_id(body.get("owner"))
    description = body.get("description") if isinstance(body.get("description"), str) else None
    return GroupInfo(
        id=group_id,
        name=name,
        participants=participants,
        owner=owner,
        description=description,
    )


def participant_change_result_from_waha(
    item: dict[str, Any], *, action: Literal["added", "removed"]
) -> ParticipantChangeResult:
    """Map one entry of WAHA's per-participant add/remove response.

    WAHA answers group participant-add/remove with one outcome per
    requested id rather than a single all-or-nothing result — WhatsApp
    itself silently refuses some adds when the target's privacy
    settings block group invites, which WAHA surfaces as a
    non-success per-participant status rather than a client-level
    error.

    NOC-REMEDIATE[waha-verify]: the exact status/code WAHA emits for the
    privacy-refusal case (mapped here to `"invite_required"` for any
    `401`/`403`) is inferred from the WAHA Groups API's documented
    shape, not confirmed against a live add on the fleet session (no
    live-WAHA read access in this dispatch — see the delivery note).
    Confirm the real codes before this path carries production bulk-add
    traffic. — 2026-09-16
    """
    participant_id = normalize_waha_id(item.get("id")) or ""
    code = item.get("status") if isinstance(item.get("status"), int) else item.get("code")
    outcome: Literal["added", "removed", "invite_required", "failed"]
    if code is None or code in (200, 201):
        outcome = action
    elif code in (401, 403):
        outcome = "invite_required"
    else:
        outcome = "failed"
    return ParticipantChangeResult(id=participant_id, outcome=outcome, code=code)
