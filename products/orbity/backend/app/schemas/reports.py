"""
Pydantic schemas for the /api/reports endpoints.

StrictHttpModel (extra="forbid") on all inbound models.
Outbound models use extra="ignore" (DB may return extra columns).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field, model_validator

from noctusai_lib.api import StrictHttpModel

StatusLiteral = Literal["draft", "published"]


# ---------------------------------------------------------------------------
# Report inbound
# ---------------------------------------------------------------------------

class ReportCreate(StrictHttpModel):
    client_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    period_start: date
    period_end: date
    config: dict[str, Any] = Field(default_factory=dict)
    status: StatusLiteral = "draft"
    expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def period_end_after_start(self) -> "ReportCreate":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class ReportUpdate(StrictHttpModel):
    client_id: Optional[UUID] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    config: Optional[dict[str, Any]] = None
    status: Optional[StatusLiteral] = None
    expires_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Report outbound
# ---------------------------------------------------------------------------

class ReportOut(StrictHttpModel):
    """Outbound — allow extra columns from DB without error."""

    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    client_id: Optional[UUID] = None
    name: str
    public_token: UUID
    period_start: date
    period_end: date
    config: dict[str, Any] = Field(default_factory=dict)
    status: str
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Report snapshot outbound
# ---------------------------------------------------------------------------

class ReportSnapshotOut(StrictHttpModel):
    """Outbound snapshot — allow extra DB columns."""

    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    report_id: UUID
    generated_at: datetime
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Public report response (token-gated, unauthenticated)
# ---------------------------------------------------------------------------

class PublicReportOut(StrictHttpModel):
    """Returned by GET /api/reports/public/{token}.

    Exposes the report metadata + latest snapshot payload.
    No org_id, no public_token — intentionally minimal for the end-client view.
    """

    model_config = {"extra": "ignore"}

    report_id: UUID
    name: str
    period_start: date
    period_end: date
    status: str
    expires_at: Optional[datetime] = None
    snapshot_id: Optional[UUID] = None
    generated_at: Optional[datetime] = None
    payload: dict[str, Any] = Field(default_factory=dict)
