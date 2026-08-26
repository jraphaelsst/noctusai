"""Pydantic schemas for the Settings router.

Boundary types — never let the credential bundle (refresh_token,
access_token) leak into a response model. The ``KeysStatus`` shape is
deliberately read-only.

NOTE — the YouTube-specific schemas (``YouTubeStatus`` / ``YouTubeAuthURL``)
moved to ``app.modules.youtube.schemas.settings`` in Phase 8 alongside
the YouTube routes. ``KeysStatus`` stays here because it enumerates
secrets for every integration (YouTube, Vista, Waha, Email, OpenAI, ...)
— a cross-domain shape, not a YouTube-domain one.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


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
    #: Scope this recipient to one client. `None` = ORG-WIDE: the fallback
    #: tier that hears about anything not claimed by a specific client. That
    #: tier is what stops an unattributed lead from alerting nobody, so it
    #: should rarely be empty.
    marca_id: str | None = None

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
    #: Re-scope an existing recipient. Handled via `model_fields_set` rather
    #: than the shared `exclude_none` path, so sending an explicit `null`
    #: CLEARS the scope back to org-wide while omitting the key leaves it
    #: untouched. Without that distinction a recipient could be scoped to a
    #: client and never returned to org-wide through the API.
    marca_id: str | None = None
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
    marca_id: str | None = None
    created_at: datetime


# ─── API Keys tab ──────────────────────────────────────────────────────
KeyHealth = Literal["configured", "missing"]


class KeyStatusEntry(BaseModel):
    label: str
    health: KeyHealth
    description: str


class KeysStatus(BaseModel):
    """Aggregate health for the API Keys tab. Built from SocialWiringSettings;
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
    text: str = "Teste do Social Wiring via WAHA."


class WahaTestResult(BaseModel):
    ok: bool
    phone: str
    message_id: str | None = None
    error: str | None = None


# ─── Meta App config (Wave 2 — app-wide, DB-backed + env-fallback) ─────
class MetaAppConfigUpdate(BaseModel):
    """Inbound payload for PUT /settings/meta-app.

    ``app_secret`` is write-only and OPTIONAL: omitted/blank leaves the
    stored secret untouched (never overwritten by an accidental blank
    submit — the FE never pre-fills it, so a re-save without editing the
    secret must not silently wipe it). At least one field must be set.
    """

    app_id: str | None = None
    app_secret: str | None = None

    class Config:
        extra = "forbid"


class MetaAppConfigStatus(BaseModel):
    """Outbound shape for PUT/GET /settings/meta-app* — NEVER the secret
    itself, only whether each half of the pair is configured (DB or
    env) plus a masked App ID for display confirmation."""

    app_id_configured: bool
    app_secret_configured: bool
    app_id_masked: str | None = None


# ─── Instagram App config (byte-for-byte mirror of MetaAppConfig*, keyed
# on the Instagram Business Login app credential pair) ──────────────────
class InstagramAppConfigUpdate(BaseModel):
    """Inbound payload for PUT /settings/instagram-app.

    ``app_secret`` is write-only and OPTIONAL: omitted/blank leaves the
    stored secret untouched (never overwritten by an accidental blank
    submit — the FE never pre-fills it, so a re-save without editing the
    secret must not silently wipe it). At least one field must be set.
    """

    app_id: str | None = None
    app_secret: str | None = None

    class Config:
        extra = "forbid"


class InstagramAppConfigStatus(BaseModel):
    """Outbound shape for PUT/GET /settings/instagram-app* — NEVER the
    secret itself, only whether each half of the pair is configured (DB
    or env) plus a masked App ID for display confirmation."""

    app_id_configured: bool
    app_secret_configured: bool
    app_id_masked: str | None = None


# ─── document retention policy (migration 079) ─────────────────────────
class DocumentoRetencaoPolitica(BaseModel):
    """One row of the retention screen.

    Carries the effective value AND the platform default it may be
    overriding, because the screen has to render "5 anos (padrão: 10 anos)"
    and offer a restore — and a second request to learn the default would
    make the two halves able to disagree.

    `retencao_dias = None` means "manter indefinidamente" and is a real
    policy, not a missing value. `ancora` names what the countdown starts
    from (`envio` for cliente documents, `encerramento` for a deal's) —
    without it a duration on screen is ambiguous, and a user reading "5 anos"
    would have no way to know five years from what.
    """

    superficie: Literal["cliente", "atendimento"]
    tipo_documento: str
    retencao_dias: int | None
    padrao_dias: int | None
    personalizado: bool
    motivo: str | None = None
    padrao_motivo: str | None = None
    ancora: Literal["envio", "encerramento"]
    ancora_rotulo: str
    atualizado_em: datetime | None = None
    atualizado_por: str | None = None


class DocumentoRetencaoLista(BaseModel):
    """Outbound shape for GET /settings/documento-retencao."""

    items: list[DocumentoRetencaoPolitica]
    total: int


class DocumentoRetencaoUpdate(BaseModel):
    """Inbound payload for PUT /settings/documento-retencao.

    `retencao_dias = null` is an explicit choice — keep indefinitely — and is
    stored as an override row rather than by clearing the org's row, because
    "the controller decided to keep these forever" and "the controller never
    touched this" are different facts. Use DELETE for the second.

    `ge=1`, not `ge=0`: zero would mean "expire the instant the clock starts",
    which nobody sets deliberately, and it collides with the falsy check the
    upload path uses. Mirrors migration 079's CHECK.
    """

    superficie: Literal["cliente", "atendimento"]
    tipo_documento: str = Field(min_length=1, max_length=100)
    retencao_dias: int | None = Field(default=None, ge=1)
    motivo: str | None = Field(default=None, max_length=500)

    class Config:
        extra = "forbid"


# ─── clientes inactivity threshold (D16, roadmap lead-card-hub-2026-08) ─
class ClientesInactivityConfigUpdate(BaseModel):
    """Inbound payload for PUT /settings/clientes-inactivity.

    `threshold_days = 0` is a valid, meaningful value: it explicitly
    disables the inactivity sweep for this org. There is no separate
    "unset" wire value — the DISTINCT "never configured, use the
    platform default" state is represented by there being no row at all
    for this org (`clientes_inactivity_config`), which this write
    endpoint can never produce (a PUT always upserts a row). See
    `app/services/clientes_inactivity_service.py`'s module docstring for
    the full unconfigured-vs-disabled reasoning."""

    threshold_days: int = Field(ge=0)

    class Config:
        extra = "forbid"


class ClientesInactivityConfigStatus(BaseModel):
    """Outbound shape for PUT/GET /settings/clientes-inactivity.

    `configured` distinguishes "this org has its own stored value"
    (`threshold_days` is that value) from "falling back to the platform
    default" (`threshold_days` is `clientes_inactivity_threshold_days_
    default`, currently 180) — a Settings UI needs this to render
    "using the default (180)" vs. "set to 45" correctly."""

    threshold_days: int
    configured: bool
    default_threshold_days: int
