"""Pydantic In/Out schemas for the Meta connector MCP tools.

One In + one Out model per tool (vista's `types.py` shape). Out models
are JSON-friendly mirrors of the seed value objects the tool wraps —
the tool never leaks a raw seed dataclass; it maps into these.

Only the SHIPPED WhatsApp slice has schemas here. The Facebook /
Instagram / diagnostics schemas are deliberately absent — their backing
seed package (`noctusai_lib.integrations.meta`) does not exist; see
`mcp/meta/README.md`.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ─── meta.whatsapp.send_text ─────────────────────────────────────────────


class SendTextInput(BaseModel):
    """Send a WhatsApp text message via WAHA.

    OUTBOUND SIDE-EFFECT. `confirm` MUST be `True` or the handler returns
    a typed error WITHOUT sending (confirm-then-execute, `KB §
    PATTERNS/llm-bot-security.md`). The host LLM must set it explicitly.
    """

    phone: str = Field(
        ...,
        description="Recipient phone in international format, digits only "
        "(e.g. '5511999998888'). Converted to a WAHA chat_id internally.",
    )
    text: str = Field(..., min_length=1, description="Message body to send.")
    confirm: bool = Field(
        False,
        description="MUST be true to actually send. When false/omitted the "
        "tool returns a typed error and performs NO side-effect — this is "
        "the confirm-then-execute gate for an outbound action.",
    )


class SendTextOutput(BaseModel):
    sent: bool
    chat_id: Optional[str] = None
    provider_response: Optional[dict] = None
    error: Optional[dict] = None


# ─── meta.whatsapp.parse_inbound ─────────────────────────────────────────


class ParseInboundInput(BaseModel):
    """Parse a raw WAHA webhook payload into the normalized inbound shape.

    PURE — no side-effect, no confirm gate. Wraps the seed
    `parse_waha_inbound_message` parser so an agent can inspect what an
    inbound WAHA event would decode to without standing up a webhook.
    """

    payload: dict = Field(
        ..., description="Raw WAHA webhook JSON body (the POST the WAHA "
        "server delivers to a webhook receiver)."
    )


class ParseInboundOutput(BaseModel):
    provider_message_id: Optional[str] = None
    chat_id: Optional[str] = None
    from_phone: Optional[str] = None
    text: Optional[str] = None
    session: Optional[str] = None
    from_name: Optional[str] = None
    media_url: Optional[str] = None
    media_mimetype: Optional[str] = None
    error: Optional[dict] = None
class FacebookPageOut(BaseModel):
    """JSON-friendly mirror of the seed `FacebookPage` value object.

    `access_token` is intentionally OMITTED — it is a per-Page Graph
    token the seed value object carries transiently; an MCP tool must
    never leak a credential to the host LLM.
    """

    id: str
    name: str
    category: Optional[str] = None
    fan_count: Optional[int] = None
    followers_count: Optional[int] = None
    link: Optional[str] = None
    tasks: List[str] = Field(default_factory=list)


class FacebookPostOut(BaseModel):
    """JSON-friendly mirror of the seed `FacebookPost` value object."""

    id: str
    message: Optional[str] = None
    created_time: Optional[str] = None
    permalink_url: Optional[str] = None
    full_picture: Optional[str] = None
    likes: int = 0
    comments: int = 0
    shares: int = 0
    attachments: List[dict] = Field(default_factory=list)


class InstagramAccountOut(BaseModel):
    """JSON-friendly mirror of the seed `InstagramAccount` value object."""

    id: str
    username: str
    name: Optional[str] = None
    profile_picture_url: Optional[str] = None
    followers_count: Optional[int] = None
    follows_count: Optional[int] = None
    media_count: Optional[int] = None
    biography: Optional[str] = None
    website: Optional[str] = None
    page_id: Optional[str] = None


class InstagramMediaOut(BaseModel):
    """JSON-friendly mirror of the seed `InstagramMedia` value object."""

    id: str
    caption: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    permalink: Optional[str] = None
    thumbnail_url: Optional[str] = None
    timestamp: Optional[str] = None
    like_count: int = 0
    comments_count: int = 0


class PostInsightsOut(BaseModel):
    """JSON-friendly mirror of the seed `PostInsights` value object."""

    object_id: str
    metrics: dict = Field(default_factory=dict)
    raw: List[dict] = Field(default_factory=list)


# ─── meta.facebook.list_pages ────────────────────────────────────────────


class ListPagesInput(BaseModel):
    """List the Facebook Pages the authenticated identity manages.

    PURE read — no side-effect, no confirm gate. Wraps the seed
    `MetaAdapter.list_facebook_pages()`. With no Meta creds configured
    the seed factory returns `FakeMetaAdapter`, so this answers
    deterministically (empty unless seeded) — the deferred-config rule.
    """


class ListPagesOutput(BaseModel):
    pages: List[FacebookPageOut] = Field(default_factory=list)
    auth_mode: Optional[str] = None
    error: Optional[dict] = None


# ─── meta.facebook.list_page_posts ───────────────────────────────────────


class ListPagePostsInput(BaseModel):
    """List posts authored by a Facebook Page (read-only)."""

    page_id: str = Field(..., description="The Facebook Page id.")
    limit: int = Field(
        25, ge=1, le=100, description="Max posts to return (paging cap)."
    )


class ListPagePostsOutput(BaseModel):
    posts: List[FacebookPostOut] = Field(default_factory=list)
    auth_mode: Optional[str] = None
    error: Optional[dict] = None


# ─── meta.facebook.post_insights ─────────────────────────────────────────


class PostInsightsInput(BaseModel):
    """Fetch flattened insight metrics for a single Facebook post."""

    post_id: str = Field(..., description="The Facebook post id.")
    page_id: Optional[str] = Field(
        None, description="Owning Page id (optional; aids token selection)."
    )


class PostInsightsOutput(BaseModel):
    insights: Optional[PostInsightsOut] = None
    auth_mode: Optional[str] = None
    error: Optional[dict] = None


# ─── meta.instagram.list_accounts ────────────────────────────────────────


class ListAccountsInput(BaseModel):
    """List the Instagram Business/Creator accounts linked to Pages."""


class ListAccountsOutput(BaseModel):
    accounts: List[InstagramAccountOut] = Field(default_factory=list)
    auth_mode: Optional[str] = None
    error: Optional[dict] = None


# ─── meta.instagram.list_media ───────────────────────────────────────────


class ListMediaInput(BaseModel):
    """List media items for an Instagram Business account (read-only)."""

    ig_user_id: str = Field(..., description="The Instagram user/account id.")
    limit: int = Field(
        25, ge=1, le=100, description="Max media to return (paging cap)."
    )


class ListMediaOutput(BaseModel):
    media: List[InstagramMediaOut] = Field(default_factory=list)
    auth_mode: Optional[str] = None
    error: Optional[dict] = None


# ─── meta.instagram.media_insights ───────────────────────────────────────


class MediaInsightsInput(BaseModel):
    """Fetch flattened insight metrics for a single Instagram media item."""

    media_id: str = Field(..., description="The Instagram media id.")


class MediaInsightsOutput(BaseModel):
    insights: Optional[PostInsightsOut] = None
    auth_mode: Optional[str] = None
    error: Optional[dict] = None


# ─── meta.diagnostics.connection_status ──────────────────────────────────


class ConnectionStatusInput(BaseModel):
    """Introspect the active Meta adapter (read-only, no side-effect).

    Surfaces `auth_mode` (`system_user` / `user_oauth` / `none`) so the
    operator can immediately tell which auth backend is live — the
    silent-empty-data failure mode on Business-Portfolio-owned assets is
    invisible otherwise.
    """


class ConnectionStatusOutput(BaseModel):
    configured: Optional[bool] = None
    adapter: Optional[str] = None
    auth_mode: Optional[str] = None
    consent_required: Optional[bool] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    pages_count: int = 0
    instagram_accounts_count: int = 0
    status_error: Optional[str] = None
    error: Optional[dict] = None


# ─── meta.diagnostics.discover_scopes ────────────────────────────────────


class DiscoverScopesInput(BaseModel):
    """Resolve the OAuth scope set the configured Meta app should request.

    Wraps the seed `resolve_oauth_scopes` — explicit list verbatim, else
    `discover_app_permissions` when app creds are present, else the
    `META_KITCHEN_SINK_SCOPES` safety net. PURE (one best-effort Graph
    read for discovery; falls back, never raises).
    """

    configured_scopes: Optional[str] = Field(
        None,
        description="Explicit comma-separated scope list, or 'auto'/empty "
        "to trigger discovery against the configured app creds.",
    )


class DiscoverScopesOutput(BaseModel):
    scopes: List[str] = Field(default_factory=list)
    source: str = Field(
        ...,
        description="'explicit' (verbatim list), 'discovered' (Graph "
        "app-permissions), or 'kitchen_sink' (safety-net default).",
    )
    error: Optional[dict] = None


# ─── Write / ads surface (additive) ──────────────────────────────────────

_CONFIRM = Field(
    default=False,
    description=(
        "WRITE GATE — must be explicitly true. False (default) returns a "
        "typed error and performs NO mutation. Real path additionally "
        "requires the App-Review-approved scope; absent → typed error "
        "with requires_app_review=true (never a faked success)."
    ),
)


class PublishPostInput(BaseModel):
    page_id: str = Field(description="Target Facebook Page id.")
    message: str = Field(description="Post body text.")
    link: Optional[str] = Field(default=None, description="Optional link to attach.")
    photo_url: Optional[str] = Field(
        default=None, description="Optional public photo URL to attach."
    )
    confirm: bool = _CONFIRM


class PublishedPostOut(BaseModel):
    id: str
    page_id: str
    message: Optional[str] = None
    permalink_url: Optional[str] = None


class PublishPostOutput(BaseModel):
    published: Optional[PublishedPostOut] = None
    auth_mode: str = "none"
    error: Optional[dict] = None


class PublishMediaInput(BaseModel):
    ig_user_id: str = Field(description="Target Instagram user id.")
    image_url: str = Field(description="Public image URL (Graph fetches it).")
    caption: Optional[str] = Field(default=None, description="Optional caption.")
    confirm: bool = _CONFIRM


class PublishedMediaOut(BaseModel):
    id: str
    ig_user_id: str
    container_id: Optional[str] = None
    caption: Optional[str] = None
    permalink: Optional[str] = None


class PublishMediaOutput(BaseModel):
    published: Optional[PublishedMediaOut] = None
    auth_mode: str = "none"
    error: Optional[dict] = None


class AdCampaignOut(BaseModel):
    id: str
    name: Optional[str] = None
    objective: Optional[str] = None
    status: Optional[str] = None
    effective_status: Optional[str] = None


class AdSetOut(BaseModel):
    id: str
    name: Optional[str] = None
    status: Optional[str] = None
    effective_status: Optional[str] = None
    campaign_id: Optional[str] = None
    daily_budget: Optional[int] = None
    billing_event: Optional[str] = None
    optimization_goal: Optional[str] = None


class AdCreativeOut(BaseModel):
    id: str
    name: Optional[str] = None


class AdOut(BaseModel):
    id: str
    name: Optional[str] = None
    status: Optional[str] = None
    effective_status: Optional[str] = None
    adset_id: Optional[str] = None
    creative_id: Optional[str] = None


class AdInsightsOut(BaseModel):
    object_id: str
    level: str
    metrics: dict = Field(default_factory=dict)


class ListCampaignsInput(BaseModel):
    ad_account_id: str = Field(description="Ad account id (act_<id> or bare id).")


class ListCampaignsOutput(BaseModel):
    campaigns: List[AdCampaignOut] = Field(default_factory=list)
    auth_mode: str = "none"
    error: Optional[dict] = None


class AdInsightsInput(BaseModel):
    object_id: str = Field(description="Campaign / ad-set / ad id to report on.")
    level: str = Field(description="'campaign' | 'adset' | 'ad'.")
    date_preset: Optional[str] = Field(
        default=None, description="e.g. 'last_7d', 'lifetime'. None → API default."
    )


class AdInsightsOutput(BaseModel):
    insights: Optional[AdInsightsOut] = None
    auth_mode: str = "none"
    error: Optional[dict] = None


class CreateCampaignInput(BaseModel):
    ad_account_id: str = Field(description="Ad account id.")
    name: str
    objective: str = Field(description="Meta campaign objective enum.")
    special_ad_categories: List[str] = Field(default_factory=list)
    confirm: bool = _CONFIRM


class CreateCampaignOutput(BaseModel):
    campaign: Optional[AdCampaignOut] = None
    auth_mode: str = "none"
    error: Optional[dict] = None


class CreateAdSetInput(BaseModel):
    ad_account_id: str
    name: str
    campaign_id: str
    daily_budget: int = Field(description="Minor units (cents).")
    billing_event: str
    optimization_goal: str
    confirm: bool = _CONFIRM


class CreateAdSetOutput(BaseModel):
    ad_set: Optional[AdSetOut] = None
    auth_mode: str = "none"
    error: Optional[dict] = None


class CreateAdCreativeInput(BaseModel):
    ad_account_id: str
    name: str
    confirm: bool = _CONFIRM


class CreateAdCreativeOutput(BaseModel):
    creative: Optional[AdCreativeOut] = None
    auth_mode: str = "none"
    error: Optional[dict] = None


class CreateAdInput(BaseModel):
    ad_account_id: str
    name: str
    adset_id: str
    creative_id: str
    confirm: bool = _CONFIRM


class CreateAdOutput(BaseModel):
    ad: Optional[AdOut] = None
    auth_mode: str = "none"
    error: Optional[dict] = None


class UpdateCampaignStatusInput(BaseModel):
    campaign_id: str
    status: str = Field(description="e.g. 'ACTIVE' | 'PAUSED' | 'ARCHIVED'.")
    confirm: bool = _CONFIRM


class UpdateCampaignStatusOutput(BaseModel):
    campaign: Optional[AdCampaignOut] = None
    auth_mode: str = "none"
    error: Optional[dict] = None


class UpdateAdSetBudgetInput(BaseModel):
    ad_set_id: str
    daily_budget: int = Field(description="New daily budget, minor units.")
    confirm: bool = _CONFIRM


class UpdateAdSetBudgetOutput(BaseModel):
    ad_set: Optional[AdSetOut] = None
    auth_mode: str = "none"
    error: Optional[dict] = None


__all__ = [
    "PublishPostInput",
    "PublishedPostOut",
    "PublishPostOutput",
    "PublishMediaInput",
    "PublishedMediaOut",
    "PublishMediaOutput",
    "AdCampaignOut",
    "AdSetOut",
    "AdCreativeOut",
    "AdOut",
    "AdInsightsOut",
    "ListCampaignsInput",
    "ListCampaignsOutput",
    "AdInsightsInput",
    "AdInsightsOutput",
    "CreateCampaignInput",
    "CreateCampaignOutput",
    "CreateAdSetInput",
    "CreateAdSetOutput",
    "CreateAdCreativeInput",
    "CreateAdCreativeOutput",
    "CreateAdInput",
    "CreateAdOutput",
    "UpdateCampaignStatusInput",
    "UpdateCampaignStatusOutput",
    "UpdateAdSetBudgetInput",
    "UpdateAdSetBudgetOutput",
    "SendTextInput",
    "SendTextOutput",
    "ParseInboundInput",
    "ParseInboundOutput","FacebookPageOut", "FacebookPostOut", "InstagramAccountOut", "InstagramMediaOut", "PostInsightsOut", "ListPagesInput", "ListPagesOutput", "ListPagePostsInput", "ListPagePostsOutput", "PostInsightsInput", "PostInsightsOutput", "ListAccountsInput", "ListAccountsOutput", "ListMediaInput", "ListMediaOutput", "MediaInsightsInput", "MediaInsightsOutput", "ConnectionStatusInput", "ConnectionStatusOutput", "DiscoverScopesInput", "DiscoverScopesOutput"
]
