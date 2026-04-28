"""
Consent Schemas — auditable consent records per session (compliance-audit-
reconciliation Phase 5, Q5).

Consent is persisted per (appointment, scope) pair; each scope is granted
and revoked independently. See `therapy.consent_records` + migration
`008_consent_retention.sql`.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


ConsentScope = Literal["recording", "transcription", "ai_summary", "longitudinal"]


class ConsentGrantRequest(BaseModel):
    appointment_id: str
    scope: ConsentScope
    policy_version: str = Field(..., min_length=1, max_length=64)
    purpose_text: str = Field(..., min_length=1)


class ConsentRevokeRequest(BaseModel):
    appointment_id: str
    scope: ConsentScope
    reason: Optional[str] = Field(None, max_length=500)
