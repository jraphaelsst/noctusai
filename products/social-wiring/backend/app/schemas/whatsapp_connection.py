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

Contract v3 (whatsapp-realtime-inbox, Slice 5) — BREAKING for the chat
inbox shapes:
  - ``GET /{id}/chats`` and ``GET /{id}/chats/{chatId}/messages`` return a
    keyset-paginated envelope (``{items, next_before}``), not a bare array.
    The old ``ChatSummary`` DTO (contact/last_message/unread, WAHA-merge
    era) is replaced by ``ChatDTO`` (title/last_message_preview/
    unread_count/last_read_at/archived/pinned — the
    ``WhatsAppChatStore.ChatSummary`` dataclass's wire shape verbatim).
  - ``MessageOut``/``MessageDTO`` (alias) gained ``ack``/``acked_at``
    (migration 040 delivery-ack tracking).
  - New: ``ChatReadRequest``/``ChatReadOut`` (``POST .../read``),
    ``WhatsAppConnectionRecoverOut`` (``POST /{id}/recover``).
  - ``DEFAULT_WHATSAPP_WEBHOOK_EVENTS`` is the single source of truth for
    the inbound event set both ``create_connection`` and
    ``WhatsAppWebhookConfigRequest`` register.
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

    ``client_id`` (migration 017): optional UUID linking the new connection
    to an existing cliente.  Absent / null = unassigned.
    """

    label: str = Field(..., min_length=1, max_length=120)
    api_key: str = Field(..., min_length=1, max_length=2048)
    # Migration 017 — optional cliente ownership at creation time.
    client_id: Optional[UUID] = Field(
        default=None,
        description="Optional clients.id to link this connection to a cliente.",
    )


class BoundChat(BaseModel):
    """One entry in the per-connection ``bound_chats`` list.

    ``chat_id`` is the WhatsApp JID of a chat the agent should listen to
    (e.g. ``5511999887766@c.us`` for a DM, ``12027986...@g.us`` for a
    group).  ``label`` is an optional display name for the FE — not used
    by the intake logic.

    Stored as a JSONB array in ``whatsapp_connections.bound_chats``.  The
    intake service normalises both raw and suffix-stripped forms for
    matching, so ``5511999887766@c.us`` and ``5511999887766`` both hit.
    """

    chat_id: str = Field(..., min_length=1, max_length=128)
    label: str = Field(default="", max_length=200)


class WhatsAppConnectionUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=120)
    # Re-supply the key only when rotating it; absent = keep the stored one.
    api_key: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    base_url: Optional[str] = Field(default=None, max_length=2048)
    session_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    webhook_url: Optional[str] = Field(default=None, max_length=2048)
    # Per-connection intake config (migration 016).
    # Use model_fields_set to distinguish "not supplied" from "supplied as []".
    # None (field absent from request) = keep current value.
    # [] (explicit empty list) = clear → means "allow all" / "listen to all".
    authorized_numbers: Optional[list[str]] = Field(
        default=None,
        description=(
            "Phone numbers / JIDs allowed to trigger the agent. "
            "Empty list = all numbers allowed (not disabled — differs from the "
            "global env var). Absent field = keep current value."
        ),
    )
    bound_chats: Optional[list[BoundChat]] = Field(
        default=None,
        description=(
            "Chats the agent listens to. Empty list = all chats. "
            "Absent field = keep current value."
        ),
    )
    # Migration 017 — optional cliente FK.
    # Absent (field not in request) = keep current value.
    # Null (explicit null) = clear the link (unassign from cliente).
    # UUID = set the link.
    # Uses model_fields_set to distinguish "not supplied" from "supplied as null".
    client_id: Optional[UUID] = Field(
        default=None,
        description=(
            "Optional clients.id. "
            "Absent = keep current; null = unassign; UUID = assign to cliente."
        ),
    )


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
    ``authorized_numbers`` / ``bound_chats`` added by migration 016:
      - authorized_numbers: empty list = all numbers allowed.
      - bound_chats: empty list = all chats listened to.
    """

    id: UUID
    label: str
    base_url: str
    session_name: str
    webhook_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    auto_reply_enabled: bool = False
    # Migration 016 — per-connection intake configuration.
    authorized_numbers: list[str] = []
    bound_chats: list[BoundChat] = []
    # Migration 017 — optional cliente ownership.
    client_id: Optional[UUID] = None


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


class WhatsAppConnectionRecoverOut(BaseModel):
    """Response for ``POST /{id}/recover`` — the converged state after the
    seed's start→restart→logout+start escalation ladder."""

    connection_id: UUID
    status: Optional[str] = Field(
        default=None, description="WAHA session status after the ladder converged."
    )
    paired: bool = False
    stage: str = Field(
        ...,
        description=(
            "Which rung the ladder converged at: already_working / start / "
            "restart / logout_start."
        ),
    )


# Migration 040 / Slice 5 — the full inbound event set. `message.ack` /
# `message.reaction` feed the realtime bus; `message.any` is WAHA's echo of
# OUR OWN outbound sends, which is what keeps `whatsapp_chats` current for a
# just-sent message WITHOUT `POST .../send` writing it directly (see
# `whatsapp_connections_router.create_connection`'s webhook registration and
# `configure_connection_webhook`'s default, both sourced from this constant).
DEFAULT_WHATSAPP_WEBHOOK_EVENTS: list[str] = [
    "message",
    "message.any",
    "message.ack",
    "message.reaction",
    "session.status",
]


class WhatsAppWebhookConfigRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    events: list[str] = Field(
        default_factory=lambda: list(DEFAULT_WHATSAPP_WEBHOOK_EVENTS)
    )


class WhatsAppWebhookResultOut(BaseModel):
    connection_id: UUID
    ok: bool
    url: str
    events: list[str]
    status: Optional[str] = None


# ── Per-connection chat inbox — pure Postgres (044_whatsapp_inbox_realtime) ──
# `ChatDTO` is the wire shape of `app.services.whatsapp_chat_store.ChatSummary`
# (a dataclass — see its `.as_dict()`, which this model's field set mirrors
# exactly; the two are the SAME wire contract realized twice, one per layer).

class ChatDTO(BaseModel):
    """Inbox summary row: one entry per conversation on a connection,
    sourced from ``social_wiring.whatsapp_chats`` (migration 040) — no
    per-request WAHA round-trip, no JID-alias merge (identity dedup happens
    at INGEST time, not read time; see the initiative's Slice 5 note).

    ``chat_id`` is the canonical send JID as ingest recorded it.
    ``title`` is the best available display label — falls back to the
    phone digits (never blank) when no contact name has been resolved.
    ``last_message_at`` / ``last_read_at`` are ISO 8601 UTC strings or
    ``null`` (never ``""`` — avoids "Invalid Date" in the FE).
    ``unread_count`` is 0 when there is nothing unread (never null).
    """

    chat_id: str
    title: str
    last_message_at: Optional[str] = None
    last_message_preview: str
    last_direction: Optional[str] = Field(default=None, pattern="^(inbound|outbound)$")
    unread_count: int = Field(..., ge=0)
    last_read_at: Optional[str] = None
    archived: bool = False
    pinned: bool = False


class ChatsPage(BaseModel):
    """Keyset-paginated envelope for ``GET /{id}/chats``."""

    items: list[ChatDTO]
    next_before: Optional[str] = Field(
        default=None,
        description=(
            "Pass back as ?before= to page further into history; null = "
            "no more history."
        ),
    )


class ChatReadRequest(BaseModel):
    """Inbound payload for ``POST /{id}/chats/{chatId}/read``."""

    up_to_message_id: Optional[str] = Field(default=None)


class ChatReadOut(BaseModel):
    """Response for ``POST /{id}/chats/{chatId}/read`` — always
    ``unread_count: 0`` (the endpoint's whole job is clearing the badge)."""

    chat_id: str
    unread_count: int = Field(..., ge=0)
    last_read_at: Optional[str] = None


class MessageOut(BaseModel):
    """One message in a chat thread.

    ``ack`` / ``acked_at`` (migration 040) are WAHA delivery-ack tracking —
    ``None`` until the ack webhook lands (``ack`` levels: -1 error, 0
    pending, 1 server, 2 device, 3 read, 4 played)."""

    id: str
    chat_id: str = Field(..., description="WhatsApp contact JID (raw_sender)")
    direction: str = Field(..., pattern="^(inbound|outbound)$")
    body: str
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")
    provider_message_id: Optional[str] = None
    structured_payload: Optional[dict] = None
    ack: Optional[int] = Field(default=None, ge=-1, le=4)
    acked_at: Optional[str] = None


# Wire-contract alias — the initiative brief names this shape `MessageDTO`;
# it is IDENTICAL to `MessageOut` (the field set `/send` already returned,
# now carrying `ack`/`acked_at` too), so this is a plain alias rather than a
# duplicate class. See `MessageOut`'s docstring for field semantics.
MessageDTO = MessageOut


class MessagesPage(BaseModel):
    """Keyset-paginated envelope for ``GET /{id}/chats/{chatId}/messages``."""

    items: list[MessageDTO]
    next_before: Optional[str] = Field(
        default=None,
        description=(
            "Pass back as ?before= to page further into history; null = "
            "no more history."
        ),
    )


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
