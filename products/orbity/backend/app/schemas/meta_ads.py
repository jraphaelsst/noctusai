"""
Pydantic schemas for the /api/meta-ads endpoints (ad accounts, campaigns,
campaign metrics, aggregates).

StrictHttpModel (extra="forbid") on all inbound models.
Outbound models use extra="ignore" (DB may return extra columns).
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

SituationLiteral = Literal["on-track", "attention", "off"]
AdAccountStatusLiteral = Literal["active", "paused", "disconnected", "error"]
CampaignStatusLiteral = Literal["active", "paused", "archived", "deleted"]


# ---------------------------------------------------------------------------
# Ad account inbound
# ---------------------------------------------------------------------------

class AdAccountCreate(StrictHttpModel):
    client_id: Optional[UUID] = None
    external_account_id: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    status: AdAccountStatusLiteral = "active"
    # access_token_ref is a CREDENTIAL REFERENCE — never the raw token.
    # NOC-REMEDIATE[orbity-meta-ads-live]: the real vault factory injects
    # the reference when the OAuth connect flow completes.
    access_token_ref: Optional[str] = Field(default=None, max_length=1024)


class AdAccountUpdate(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    status: Optional[AdAccountStatusLiteral] = None
    access_token_ref: Optional[str] = Field(default=None, max_length=1024)
    client_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Campaign inbound
# ---------------------------------------------------------------------------

class CampaignCreate(StrictHttpModel):
    ad_account_id: UUID
    client_id: Optional[UUID] = None
    external_campaign_id: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    objective: Optional[str] = Field(default=None, max_length=100)
    status: CampaignStatusLiteral = "active"
    daily_budget: Optional[float] = Field(default=None, ge=0)
    result_metric: Optional[str] = Field(default=None, max_length=100)
    situation: SituationLiteral = "on-track"


class CampaignUpdate(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    objective: Optional[str] = Field(default=None, max_length=100)
    status: Optional[CampaignStatusLiteral] = None
    daily_budget: Optional[float] = Field(default=None, ge=0)
    result_metric: Optional[str] = Field(default=None, max_length=100)
    situation: Optional[SituationLiteral] = None


class SituationUpdateRequest(StrictHttpModel):
    """Targeted situation (gestor signal) update for a campaign."""
    situation: SituationLiteral


# ---------------------------------------------------------------------------
# Campaign metrics inbound (upsert shape for sync)
# ---------------------------------------------------------------------------

class CampaignMetricUpsert(StrictHttpModel):
    """One daily snapshot row — validated before service upsert."""
    campaign_id: UUID
    date: str = Field(..., description="ISO 8601 date string (YYYY-MM-DD)")
    spend: float = Field(..., ge=0)
    impressions: int = Field(..., ge=0)
    leads: int = Field(..., ge=0)
    cpl: Optional[float] = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Outbound models (extra="ignore" — DB may return extra columns safely)
# ---------------------------------------------------------------------------

class AdAccountOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    client_id: Optional[UUID] = None
    external_account_id: str
    name: str
    status: str
    # access_token_ref is NEVER returned to the client — scrubbed in service layer.
    connected_at: str
    created_at: str
    updated_at: str

    model_config = {"extra": "ignore"}


class CampaignOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    client_id: Optional[UUID] = None
    ad_account_id: UUID
    external_campaign_id: str
    name: str
    objective: Optional[str] = None
    status: str
    daily_budget: Optional[float] = None
    result_metric: Optional[str] = None
    situation: str
    created_at: str
    updated_at: str

    model_config = {"extra": "ignore"}


class CampaignMetricOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    campaign_id: UUID
    date: str
    spend: float
    impressions: int
    leads: int
    cpl: Optional[float] = None
    created_at: str
    updated_at: str

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Aggregate outbound — spend vs leads per client/month (cash-flow style)
# ---------------------------------------------------------------------------

class ClientMonthAggregate(StrictHttpModel):
    """Monthly aggregate per client: spend vs leads summary for the gestor view."""
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    month: str        # YYYY-MM
    total_spend: float
    total_leads: int
    avg_cpl: Optional[float] = None      # weighted average CPL across campaigns
    campaign_count: int
    on_track_count: int
    attention_count: int
    off_count: int

    model_config = {"extra": "ignore"}


class SpendLeadsAggregate(StrictHttpModel):
    """Aggregate response envelope for the /aggregate endpoint."""
    period_start: str
    period_end: str
    items: list[ClientMonthAggregate]
    total_spend: float
    total_leads: int

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Sync seam — request + response shapes
# ---------------------------------------------------------------------------

class SyncCampaignsRequest(StrictHttpModel):
    """Trigger a campaign sync for a specific ad account.

    The actual Meta API pull is behind a NOC-REMEDIATE seam in the service.
    The request carries the ad_account_id to sync.
    """
    ad_account_id: UUID


class SyncCampaignsResponse(StrictHttpModel):
    """Result of a campaign sync operation."""
    synced: int         # rows upserted
    skipped: int        # rows skipped (no change)
    errors: int         # rows that failed (logged, not raised)
    source: str         # "fake" | "live" — which adapter ran

    model_config = {"extra": "ignore"}
