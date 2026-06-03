"""
Pydantic schemas for the /api/clients endpoints.

StrictHttpModel (extra="forbid") on all inbound models — Pydantic's
silent-drop on extra keys kills writes otherwise (KB § PATTERNS/backend/
pydantic-strict-http.md).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import EmailStr, Field

from noctusai_lib.api import StrictHttpModel


# ---------------------------------------------------------------------------
# Inbound
# ---------------------------------------------------------------------------

class ClientCreate(StrictHttpModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    company: Optional[str] = Field(default=None, max_length=255)
    monthly_value: Optional[float] = Field(default=None, ge=0)
    due_date: Optional[int] = Field(default=None, ge=1, le=31)
    default_billing_type: Optional[str] = Field(default=None, max_length=50)
    billing_automation_enabled: bool = False


class ClientUpdate(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    company: Optional[str] = Field(default=None, max_length=255)
    monthly_value: Optional[float] = Field(default=None, ge=0)
    due_date: Optional[int] = Field(default=None, ge=1, le=31)
    default_billing_type: Optional[str] = Field(default=None, max_length=50)
    billing_automation_enabled: Optional[bool] = None
    active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Outbound (bare — match erp pattern: no envelope wrapper on item responses)
# ---------------------------------------------------------------------------

class ClientOut(StrictHttpModel):
    """Single client representation — returned by create / get / update."""
    id: UUID
    org_id: UUID
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    monthly_value: Optional[float] = None
    due_date: Optional[int] = None
    active: bool
    default_billing_type: Optional[str] = None
    billing_automation_enabled: bool
    report_token: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"extra": "ignore"}  # outbound: extra DB columns are safe to drop
