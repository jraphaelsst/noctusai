"""Request/response schemas for the noctusai.com public website.

Shapes are verbatim from `products/core/frontend/src/website/docs/
15-api-contract.md` §2 (the `WebsiteSettings` JSON) and §3 (the HTTP API).
Every nested model subclasses `StrictHttpModel` (not just the top level) so
an admin submitting a stray key at ANY depth 422s instead of silently
dropping — the same reasoning `KB § PATTERNS/backend/pydantic-strict-http.md`
gives for the top-level rule.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


# ─── WebsiteSettings (contract §2) ───────────────────────────────────────

class L10n(StrictHttpModel):
    pt: str
    en: str


class WhatsAppSettings(StrictHttpModel):
    number_e164: Optional[str] = None
    default_message: L10n
    float_enabled: bool = True


class SectionsSettings(StrictHttpModel):
    audiences: bool = True
    products: bool = True
    custom_builds: bool = True
    trust: bool = True
    social_proof: bool = False
    pricing: bool = True
    news: bool = False  # v1.1 — off by default (contract D-"Blog" decision)
    faq: bool = True
    hero_update_card: bool = False


class ProductEntry(StrictHttpModel):
    slug: str
    visible: bool = True
    order: int = 0
    state: Literal["disponivel", "lista_de_espera", "em_breve"] = "disponivel"
    tagline: Optional[L10n] = None


class TrustItem(StrictHttpModel):
    key: str
    icon: str
    text: L10n
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None


class SocialProofItem(StrictHttpModel):
    kind: Literal["logo", "testimonial", "metric"]
    name: str
    text: Optional[L10n] = None
    image_url: Optional[str] = None
    consent_ref: str


class FaqItem(StrictHttpModel):
    q: L10n
    a: L10n


class TrackingSettings(StrictHttpModel):
    plausible_domain: Optional[str] = None
    ga4_id: Optional[str] = None
    meta_pixel_id: Optional[str] = None


class WebsiteSettings(StrictHttpModel):
    """The single shape FE and BE share (contract §2). Validated strict at
    every depth — an admin PUT with an unknown key 422s immediately rather
    than silently dropping data the FE thought it saved."""

    site_enabled: bool = True
    signup_enabled: bool = True
    whatsapp: WhatsAppSettings
    sections: SectionsSettings
    products: List[ProductEntry] = Field(default_factory=list)
    trust_items: List[TrustItem] = Field(default_factory=list)
    social_proof_items: List[SocialProofItem] = Field(default_factory=list)
    faq: List[FaqItem] = Field(default_factory=list)
    tracking: TrackingSettings


class WebsiteSettingsUpdate(StrictHttpModel):
    """`PUT /api/admin/website/settings` body — optimistic concurrency via
    `expected_version` (contract §3, 409 `version_conflict` on mismatch)."""

    settings: WebsiteSettings
    expected_version: int


class WebsiteSettingsRollback(StrictHttpModel):
    version: int


# ─── Leads (contract §3) ──────────────────────────────────────────────────

class WebsiteLeadCreate(StrictHttpModel):
    source: Literal["waitlist", "brief", "contact"]
    name: str = Field(..., min_length=1, max_length=120)
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    profile: Optional[Literal["smb", "enterprise", "developer", "solo"]] = None
    product_interest: Optional[List[str]] = None
    message: Optional[str] = Field(default=None, max_length=2000)
    locale: Literal["pt-BR", "en"]
    consent_marketing: bool
    consent_text_version: str
    utm: Optional[dict] = None
    landing_path: Optional[str] = None
    referrer: Optional[str] = None
    turnstile_token: Optional[str] = None


class WebsiteLeadPatch(StrictHttpModel):
    stage: Optional[
        Literal["novo", "contatado", "qualificado", "proposta", "ganho", "perdido", "descartado"]
    ] = None
    owner_user_id: Optional[str] = None
    next_action: Optional[str] = None
    next_action_at: Optional[str] = None
    lost_reason: Optional[str] = None
    score: Optional[int] = None


class WebsiteLeadActivityCreate(StrictHttpModel):
    kind: Literal["note", "call", "whatsapp_out", "email_out"]
    body: str = Field(..., min_length=1, max_length=5000)


# ─── Analytics (contract §3) ──────────────────────────────────────────────

class WebsiteEventCreate(StrictHttpModel):
    event: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z_]+$")
    anon_id: Optional[str] = None
    session_id: Optional[str] = None
    path: Optional[str] = None
    props: Optional[dict] = None
