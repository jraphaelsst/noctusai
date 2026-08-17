"""Pydantic In/Out models for every `olx.*` tool.

Out models stay deliberately loose (`dict` / `list[dict]` for vendor-
shaped payloads) because the vendor contract is UNVERIFIED until Gate 1
— tightening now would encode our transcription as truth and reject the
first real body that disagrees, which is the exact failure this
connector exists to catch.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class _In(BaseModel):
    """Base for inputs — reject unknown keys so a typo'd argument is a
    loud 422 rather than a silently-ignored option."""

    model_config = {"extra": "forbid"}


# ── contract / webhook ────────────────────────────────────────────────


class DescribeContractInput(_In):
    pass


class DescribeContractOutput(BaseModel):
    contract: dict[str, Any] = Field(
        description="The full documented contract: auth, delivery, fields, "
        "enums, response semantics, retry policy, JSON Schema, sample."
    )
    verified_against_live_traffic: bool = Field(
        description="False until Gate 1 observes real deliveries. False means "
        "every statement here is a transcription of the vendor's prose, not a "
        "measurement — treat it as a hypothesis."
    )


class ValidatePayloadInput(_In):
    payload: dict[str, Any] = Field(
        description="One delivery body to check against the documented contract."
    )


class ValidatePayloadOutput(BaseModel):
    valid: bool = Field(description="True when there are no `error`-severity violations.")
    would_return_4xx: bool = Field(
        description="True when the ONE documented 4xx case applies (a listing "
        "lead with no clientListingId). Every other problem still gets a 2xx — "
        "a non-2xx costs the lead after 3 retries."
    )
    violations: list[dict[str, Any]] = Field(default_factory=list)
    parsed: Optional[dict[str, Any]] = Field(
        default=None, description="The parsed lead when the body was parseable."
    )


class RecordDeliveryInput(_In):
    payload: dict[str, Any] = Field(
        description="A REAL inbound body to add to the observed corpus."
    )
    label: Optional[str] = Field(
        default=None, description="Optional note, e.g. 'first homologation lead'."
    )
    confirm: bool = Field(
        default=False, description="Must be true — this writes a fixture file."
    )


class RecordDeliveryOutput(BaseModel):
    recorded: bool
    path: Optional[str] = None
    origin_lead_id: Optional[str] = None
    corpus_size: int = 0
    violations: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


class DiffObservedInput(_In):
    pass


class DiffObservedOutput(BaseModel):
    report: dict[str, Any] = Field(
        description="Undocumented fields, documented-but-never-seen fields, "
        "required-but-null fields, novel enum values, per-body violations."
    )
    corpus_size: int
    clean: bool
    next_step: Optional[str] = None


class SimulateInput(_In):
    lead_type: Optional[str] = Field(
        default=None, description="extraData.leadType, e.g. CONTACT_CHAT."
    )
    temperature: Optional[str] = Field(default=None, description="Baixa | Média | Alta.")
    transaction_type: Optional[str] = Field(default=None, description="RENT | SELL.")
    client_listing_id: Optional[str] = Field(
        default=None, description="Our listing id. Set null to rehearse the 4xx path."
    )
    origin_lead_id: Optional[str] = Field(
        default=None, description="Override the id — reuse one to test idempotency."
    )
    mcmv: bool = Field(
        default=False, description="Send an MCMV lead (no listing ids)."
    )
    wrong_secret: bool = Field(
        default=False,
        description="Send a deliberately wrong secret to prove the receiver 401s. "
        "Rehearsing the reject path is as important as the happy path.",
    )
    confirm: bool = Field(default=False, description="Must be true — this POSTs.")


class SimulateOutput(BaseModel):
    sent: bool
    receiver_url: Optional[str] = None
    http_status: Optional[int] = None
    latency_ms: Optional[float] = None
    interpretation: Optional[str] = Field(
        default=None,
        description="What OLX would conclude from that status — 2xx delivered, "
        "anything else retried then dropped after 14 days.",
    )
    payload: Optional[dict[str, Any]] = None
    response_body_ignored: bool = True
    error: Optional[dict[str, Any]] = None


# ── leads (outbound) ──────────────────────────────────────────────────


class LeadsPushInput(_In):
    lead_name: str = Field(description="Consumer name. Required by the vendor.")
    lead_email: Optional[str] = None
    lead_telephone: Optional[str] = None
    message: Optional[str] = None
    external_id: Optional[str] = Field(
        default=None, description="Our own id for the lead, for dedup on their side."
    )
    business_type: Optional[str] = Field(
        default=None,
        description="SALE or RENTAL. NOT the SELL/RENT the inbound webhook uses — "
        "the vendor is inconsistent across its own surfaces.",
    )
    broker_email: Optional[str] = None
    lead_origin: Optional[str] = None
    confirm: bool = Field(
        default=False, description="Must be true — this sends a real lead to OLX."
    )


class LeadsPushOutput(BaseModel):
    pushed: bool
    response: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


# ── diagnostics ───────────────────────────────────────────────────────


class ConnectionStatusInput(_In):
    pass


class ConnectionStatusOutput(BaseModel):
    ok: bool
    lead_manager_configured: bool
    receiver_configured: bool
    base_url: str
    receiver_url: Optional[str] = None
    has_api_key: bool
    has_agent_name: bool
    has_webhook_secret: bool
    contract_verified: bool
    next_step: Optional[str] = None


class ProbeInput(_In):
    pass


class ProbeOutput(BaseModel):
    results: list[dict[str, Any]]
    unexpected: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rows whose observed status contradicts a RECORDED "
        "expectation. Read this, not `results`.",
    )
    unverified: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rows with no recorded expectation yet — every row, until "
        "Gate 1. Their observed status is the input that fills the baseline in.",
    )
    probed: bool = Field(
        description="False when the connector is unconfigured and nothing was called."
    )


class ListKnownEndpointsInput(_In):
    pass


class ListKnownEndpointsOutput(BaseModel):
    endpoints: list[dict[str, Any]]
    reference_urls: dict[str, str]
    support_contacts: dict[str, str]


__all__ = [
    "ConnectionStatusInput", "ConnectionStatusOutput",
    "DescribeContractInput", "DescribeContractOutput",
    "DiffObservedInput", "DiffObservedOutput",
    "LeadsPushInput", "LeadsPushOutput",
    "ListKnownEndpointsInput", "ListKnownEndpointsOutput",
    "ProbeInput", "ProbeOutput",
    "RecordDeliveryInput", "RecordDeliveryOutput",
    "SimulateInput", "SimulateOutput",
    "ValidatePayloadInput", "ValidatePayloadOutput",
]
