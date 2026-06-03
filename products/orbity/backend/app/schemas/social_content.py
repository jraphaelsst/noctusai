"""
Pydantic schemas for /api/content/* (campaigns, posts) and the public
/api/content/approve/{token} endpoints.

StrictHttpModel (extra="forbid") on all inbound models.
Outbound models use default extra="ignore" (DB may return extra columns).
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

# ---------------------------------------------------------------------------
# Shared literals
# ---------------------------------------------------------------------------

PlatformLiteral = Literal["instagram", "facebook", "tiktok", "linkedin", "twitter"]
PostStatusLiteral = Literal["draft", "pending_approval", "approved", "revision", "published"]
CampaignStatusLiteral = Literal["active", "paused", "completed", "archived"]
ApprovalStatusLiteral = Literal["pending", "approved", "revision"]


# ---------------------------------------------------------------------------
# Campaign inbound
# ---------------------------------------------------------------------------

class CampaignCreate(StrictHttpModel):
    client_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    month: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")  # YYYY-MM
    status: CampaignStatusLiteral = "active"


class CampaignUpdate(StrictHttpModel):
    client_id: Optional[UUID] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    month: Optional[str] = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    status: Optional[CampaignStatusLiteral] = None


# ---------------------------------------------------------------------------
# Campaign outbound
# ---------------------------------------------------------------------------

class CampaignOut(StrictHttpModel):
    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    client_id: Optional[UUID] = None
    name: str
    month: str
    status: str
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Post inbound
# ---------------------------------------------------------------------------

class PostCreate(StrictHttpModel):
    campaign_id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    platform: PlatformLiteral
    caption: Optional[str] = Field(default=None, max_length=5000)
    hashtags: Optional[str] = Field(default=None, max_length=2000)
    scheduled_for: Optional[str] = None   # ISO 8601 datetime string
    status: PostStatusLiteral = "draft"
    assignee_user_id: Optional[UUID] = None
    media_url: Optional[str] = Field(default=None, max_length=2000)


class PostUpdate(StrictHttpModel):
    campaign_id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    platform: Optional[PlatformLiteral] = None
    caption: Optional[str] = Field(default=None, max_length=5000)
    hashtags: Optional[str] = Field(default=None, max_length=2000)
    scheduled_for: Optional[str] = None
    status: Optional[PostStatusLiteral] = None
    assignee_user_id: Optional[UUID] = None
    media_url: Optional[str] = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Post outbound
# ---------------------------------------------------------------------------

class PostOut(StrictHttpModel):
    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    campaign_id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    platform: str
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    scheduled_for: Optional[str] = None
    status: str
    assignee_user_id: Optional[UUID] = None
    media_url: Optional[str] = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Approval inbound — authed (create approval link)
# ---------------------------------------------------------------------------

class ApprovalCreate(StrictHttpModel):
    expires_in_days: int = Field(default=7, ge=1, le=90)


# ---------------------------------------------------------------------------
# Approval inbound — PUBLIC (client decides)
# ---------------------------------------------------------------------------

class ApprovalDecision(StrictHttpModel):
    decision: Literal["approved", "revision"]
    feedback: Optional[str] = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Approval outbound
# ---------------------------------------------------------------------------

class ApprovalOut(StrictHttpModel):
    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    post_id: UUID
    public_token: UUID
    status: str
    client_feedback: Optional[str] = None
    expires_at: str
    decided_at: Optional[str] = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Public approval fetch — limited payload sent to client (no org_id leak)
# ---------------------------------------------------------------------------

class PublicApprovalView(StrictHttpModel):
    model_config = {"extra": "ignore"}

    approval_id: UUID
    post_id: UUID
    platform: str
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    media_url: Optional[str] = None
    scheduled_for: Optional[str] = None
    approval_status: str
    expires_at: str
