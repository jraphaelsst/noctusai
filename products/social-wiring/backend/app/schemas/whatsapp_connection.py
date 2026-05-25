"""Boundary DTOs for the per-user WAHA connection "lines".

The ``/api/whatsapp/connections`` router speaks these — the stored API key
NEVER leaves the backend (no field carries it on any response). Live WAHA
state (status / QR / paired account) is fetched per-line and surfaced through
the ``*StatusOut`` / ``*QrOut`` shapes, mirroring the seed
``whatsapp_admin_router`` DTOs but addressed by ``connection_id``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── CRUD ────────────────────────────────────────────────────────────────
class WhatsAppConnectionCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    api_key: str = Field(..., min_length=1, max_length=2048)
    # Optional — the router defaults base_url to the configured WAHA server
    # so the common case is just label + API key.
    base_url: Optional[str] = Field(default=None, max_length=2048)
    session_name: str = Field(default="default", min_length=1, max_length=120)
    webhook_url: Optional[str] = Field(default=None, max_length=2048)


class WhatsAppConnectionUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=120)
    # Re-supply the key only when rotating it; absent = keep the stored one.
    api_key: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    base_url: Optional[str] = Field(default=None, max_length=2048)
    session_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    webhook_url: Optional[str] = Field(default=None, max_length=2048)


class WhatsAppConnectionOut(BaseModel):
    """A line as shown in the listing — no secret material."""

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
