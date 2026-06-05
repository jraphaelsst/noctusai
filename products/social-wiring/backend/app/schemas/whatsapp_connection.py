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
    ``session_name`` is the auto-generated unique WAHA session name
    (``sw-<hex>``) — informational, useful for WAHA dashboard correlation.
    """

    id: UUID
    label: str
    base_url: str
    session_name: str
    webhook_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


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
