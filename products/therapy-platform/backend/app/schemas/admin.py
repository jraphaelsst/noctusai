"""
Admin-specific schemas — approvals, commission overrides, patient assignments.
"""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field


class ApprovalAction(BaseModel):
    """Approve or reject an entity (therapist or clinic)."""

    action: Literal["approve", "reject"]
    reason: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Required when action is 'reject'",
    )


class CommissionOverrideCreate(BaseModel):
    """Set a platform-level commission override for a clinic or therapist."""

    target_type: Literal["clinic", "therapist"]
    target_id: str
    custom_commission_pct: float = Field(..., ge=0, le=100)


class PatientAssignment(BaseModel):
    """Admin-assign a patient to a therapist and/or clinic."""

    patient_id: str
    therapist_id: Optional[str] = None
    clinic_id: Optional[str] = None
    custom_price: Optional[float] = Field(default=None, ge=0, le=100000)
