"""Boundary DTOs for the per-user WAHA connection "lines".

The ``/api/whatsapp/connections`` router speaks these — the stored API key
NEVER leaves the backend (no field carries it on any response). Live WAHA
state (status / QR / paired account) is fetched per-line and surfaced through
the ``*StatusOut`` / ``*QrOut`` shapes, mirroring the seed
``whatsapp_admin_router`` DTOs but addressed by ``connection_id``.

Contract v2 (social-waha-connect-backend):
  - Create payload shrinks to {label, api_key}.  ``base_url``,
    ``session_name``, and ``webhook_url`` are no longer user-provided; the
    router derives them server-side. Unknown extra fields are silently ignored
    by pydantic's default; callers MUST NOT rely on extra fields being stored.
  - Response exposes ``webhook_url`` (the auto-minted per-connection token URL)
    and ``session_name`` (informational, auto-generated unique value).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── CRUD ────────────────────────────────────────────────────────────────
class WhatsAppConnectionCreate(BaseModel):
    """Inbound create payload.

    Only ``label`` and ``api_key`` are meaningful — ``base_url``,
    ``session_name``, and ``webhook_url`` are derived server-side and ignored
    if present. Extra fields are silently dropped (pydantic default) so
    existing callers that still pass them do not break.
    """

    label: str = Field(..., min_length=1, max_length=120)
    api_key: str = Field(..., min_length=1, max_length=2048)


class WhatsAppConnectionUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=120)
    # Re-supply the key only when rotating it; absent = keep the stored one.
    api_key: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    base_url: Optional[str] = Field(default=None, max_length=2048)
    session_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    webhook_url: Optional[str] = Field(default=None, max_length=2048)


class WhatsAppConnectionOut(BaseModel):
    """A line as shown in the listing — no secret material.

    ``webhook_url`` is the auto-minted per-connection inbound URL
    (``…/api/whatsapp/webhook/{token}``).  It is read-only and derived from
    the stored ``webhook_token``; callers should treat it as informational
    (display, WAHA dashboard check).
    ``session_name`` is the WAHA session name the line drives. On WAHA Core
    this is the single shared ``default`` session; on WAHA Plus it may be a
    per-connection value — informational, useful for WAHA dashboard correlation.
    ``auto_reply_enabled`` is the per-connection chatbot toggle (migration 014,
    default OFF).  When False the existing chatbot does not auto-reply; the
    operator can chat manually via the inbox UI.
    """

    id: UUID
    label: str
    base_url: str
    session_name: str
    webhook_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    auto_reply_enabled: bool = False


class WhatsAppConnectionApiKeyOut(BaseModel):
    """The decrypted API key for ONE line — returned ONLY by the explicit,
    owner-scoped reveal endpoint (``GET /{id}/api-key``).

    This is the single deliberate exception to the "secret never rides a
    response" rule that governs every other DTO here: the reveal is an explicit
    user action (the eye toggle in the connection modal), owner-scoped by the
    same auth+store filter as every live op, and never returned on a list/get
    path. Treat it as sensitive — it carries the plaintext WAHA ``X-Api-Key``.
    """

    connection_id: UUID
    api_key: str


# ─── Live WAHA state (per line) ──────────────────────────────────────────
class WhatsAppConnectionStatusOut(BaseModel):
    connection_id: UUID
    status: Optional[str] = Field(
        default=None,
        description="WAHA session status (WORKING / SCAN_QR_CODE / STARTING / …).",
    )
    paired: bool = False
    me_id: Optional[str] = None
    me_name: Optional[str] = None
    session: str
    error: Optional[str] = Field(
        default=None, description="Set when the live status probe failed."
    )


class WhatsAppConnectionQrOut(BaseModel):
    connection_id: UUID
    scannable: bool
    status: Optional[str] = None
    png_base64: Optional[str] = None


class WhatsAppWebhookConfigRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    events: list[str] = Field(
        default_factory=lambda: ["message", "message.any", "session.status"]
    )


class WhatsAppWebhookResultOut(BaseModel):
    connection_id: UUID
    ok: bool
    url: str
    events: list[str]
    status: Optional[str] = None


# ── Per-connection chat inbox (014_whatsapp_chat_per_connection) ─────────────

class ChatSummary(BaseModel):
    """Inbox summary row: one entry per WhatsApp contact (JID) on a connection.

    ``chat_id`` is the CANONICAL send JID (``<phone>@c.us``) — de-duped
    across all JID forms for the same human (``@c.us`` / ``@s.whatsapp.net``
    / ``@lid``).  When the phone cannot be resolved the raw JID is kept.

    ``contact`` is the best available display name: contacts table ``nome``
    → WAHA name/pushname → phone digits → raw LID.

    ``contact_id`` is the social_wiring.contacts.id UUID if this human has
    been registered, else ``None``.

    ``last_message_at`` is an ISO 8601 UTC string or ``null`` when there is
    no usable timestamp (avoids "Invalid Date" in the FE).

    ``unread`` is 0 when there are no unread inbound messages (never null).
    """

    chat_id: str = Field(..., description="Canonical send JID (<phone>@c.us)")
    contact: str = Field(..., description="Display label — name, phone, or raw JID")
    contact_id: Optional[str] = Field(
        default=None, description="contacts.id UUID if registered, else null"
    )
    last_message: str
    last_message_at: Optional[str] = Field(
        default=None, description="ISO 8601 UTC or null when no timestamp available"
    )
    last_direction: str = Field(..., pattern="^(inbound|outbound)$")
    unread: int = Field(..., ge=0)


class MessageOut(BaseModel):
    """One message in a chat thread."""

    id: str
    chat_id: str = Field(..., description="WhatsApp contact JID (raw_sender)")
    direction: str = Field(..., pattern="^(inbound|outbound)$")
    body: str
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")
    provider_message_id: Optional[str] = None
    structured_payload: Optional[dict] = None


class SendMessageRequest(BaseModel):
    """Inbound payload for POST …/chats/{chatId}/send.

    ``text`` must be non-empty — an empty string is rejected with 422
    (Pydantic min_length guard) before the router even calls WAHA.
    """

    text: str = Field(..., min_length=1, max_length=65536)


class AutoReplyToggleRequest(BaseModel):
    """Inbound payload for PUT …/auto-reply."""

    enabled: bool


class AutoReplyToggleOut(BaseModel):
    """Response for PUT …/auto-reply."""

    connection_id: UUID
    auto_reply_enabled: bool
