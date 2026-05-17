"""Pydantic schemas for the Settings router.

Boundary types — never let the credential bundle (refresh_token,
access_token) leak into a response model. The ``YouTubeStatus`` /
``KeysStatus`` shapes are deliberately read-only.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


# ─── YouTube tab ───────────────────────────────────────────────────────
class YouTubeStatus(BaseModel):
    """Connection state for the Settings → YouTube tab."""

    connected: bool
    channel_id: str | None = None
    channel_title: str | None = None
    subscriber_count: int | None = None
    video_count: int | None = None
    view_count: int | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None


class YouTubeAuthURL(BaseModel):
    """Response for GET /settings/youtube/auth-url."""

    auth_url: str
    state: str


# ─── Notifications tab — recipients ────────────────────────────────────
class RecipientCreate(BaseModel):
    """Inbound payload for POST /settings/recipients."""

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    whatsapp_number: str | None = Field(
        default=None,
        # E.164 lite — leading +, country code, then 8-15 digits.
        pattern=r"^\+[1-9]\d{7,14}$",
    )
    is_active: bool = True

    @model_validator(mode="after")
    def _at_least_one_channel(self) -> "RecipientCreate":
        if not self.email and not self.whatsapp_number:
            raise ValueError(
                "recipient must have at least one of: email, whatsapp_number"
            )
        return self


class RecipientUpdate(BaseModel):
    """Inbound payload for PUT /settings/recipients/{id}.

    Every field optional — omitted fields keep their stored value. The
    "at-least-one-channel" CHECK lives on the table; updates can transit
    through a momentarily-empty state if the consumer sends the right
    sequence, so we re-validate at the API boundary too.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    whatsapp_number: str | None = Field(
        default=None,
        pattern=r"^\+[1-9]\d{7,14}$",
    )
    is_active: bool | None = None


class RecipientOut(BaseModel):
    """Outbound shape for the recipient list."""

    id: str
    name: str
    email: str | None = None
    whatsapp_number: str | None = None
    is_active: bool
    created_at: datetime


# ─── API Keys tab ──────────────────────────────────────────────────────
KeyHealth = Literal["configured", "missing"]


class KeyStatusEntry(BaseModel):
    label: str
    health: KeyHealth
    description: str


class KeysStatus(BaseModel):
    """Aggregate health for the API Keys tab. Built from CrawlerSettings;
    never echoes the actual values back."""

    youtube_client_id: KeyStatusEntry
    youtube_client_secret: KeyStatusEntry
    youtube_redirect_uri: KeyStatusEntry
    frontend_base_url: KeyStatusEntry
    openai_api_key: KeyStatusEntry
    openai_chat_model: KeyStatusEntry
    whatsapp_chatbot_enabled: KeyStatusEntry
    encryption_key: KeyStatusEntry
    smtp_user: KeyStatusEntry
    smtp_password: KeyStatusEntry
    waha_base_url: KeyStatusEntry
    waha_api_key: KeyStatusEntry
    waha_dashboard_url: KeyStatusEntry
    waha_webhook_url: KeyStatusEntry
    waha_webhook_hmac_secret: KeyStatusEntry
    vista_base_url: KeyStatusEntry
    vista_api_key: KeyStatusEntry
    database_backend: KeyStatusEntry
    supabase_url: KeyStatusEntry
    supabase_service_role_key: KeyStatusEntry


# ─── Live integration checks ──────────────────────────────────────────
class VistaStatus(BaseModel):
    configured: bool
    ok: bool
    product_code: str
    title: str | None = None
    address: str | None = None
    price: str | None = None
    bedrooms: int | None = None
    area_sqm: float | None = None
    error: str | None = None


class EmailTestRequest(BaseModel):
    to: EmailStr | None = None


class EmailTestResult(BaseModel):
    ok: bool
    to: str
    error: str | None = None


class WahaStatus(BaseModel):
    configured: bool
    ok: bool
    base_url: str | None = None
    session: str
    status: str | None = None
    error: str | None = None


class WahaTestRequest(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    text: str = "Teste do YouTube Crawler via WAHA."


class WahaTestResult(BaseModel):
    ok: bool
    phone: str
    message_id: str | None = None
    error: str | None = None
