"""Pydantic In/Out models for every `imovelweb.*` tool.

Out models stay deliberately loose (`dict` / `list[dict]` for
vendor-shaped payloads) because the contract is UNVERIFIED until Gate 1.
Tightening now would encode our transcription as truth and reject the
first real body that disagrees — which is the exact failure this
connector exists to catch.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class _In(BaseModel):
    """Base for inputs — reject unknown keys, so a typo'd argument is a
    loud validation error rather than a silently-ignored option."""

    model_config = {"extra": "forbid"}


_LANGUAGE_HELP = (
    "Callback body language: EN | EN2 | EN_SF | ES | PT. The registered "
    "value decides the FIELD NAMES of every body the vendor pushes, not "
    "just its prose. Defaults to EN2."
)


# ── contract (zero IO, no credentials) ────────────────────────────────


class ContractDescribeInput(_In):
    language: Optional[str] = Field(default=None, description=_LANGUAGE_HELP + " Omit for all five.")


class ContractDescribeOutput(BaseModel):
    contract: dict[str, Any] = Field(
        description="Auth, delivery semantics, retry policy, and every field "
        "per language with type/required/verified/notes."
    )
    verified_against_live_traffic: bool = Field(
        description="False until Gate 1 observes real deliveries. False means "
        "every statement here is a transcription of vendor prose — a "
        "hypothesis, not a measurement. The vendor's own OpenAPI spec models "
        "ZERO callback bodies, so nothing here is confirmable from a "
        "machine-readable source."
    )
    json_schema: Optional[dict[str, Any]] = Field(
        default=None, description="JSON Schema for the requested language."
    )


class ContractValidatePayloadInput(_In):
    payload: dict[str, Any] = Field(description="One delivery body to check.")
    language: Optional[str] = Field(
        default=None,
        description=_LANGUAGE_HELP + " Omit to auto-detect from the field names.",
    )


class ContractValidatePayloadOutput(BaseModel):
    valid: bool = Field(
        description="True when there is no BLOCKING violation. The only "
        "blocking condition is a body with no event id — it cannot be "
        "deduplicated, so it cannot be stored safely."
    )
    detected_language: Optional[str] = None
    language_used: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=list,
        description="Everything else. A warning still gets a 2xx: refusing "
        "one requeues a real lead for 72 hours against a body that will "
        "never change.",
    )
    parsed: Optional[dict[str, Any]] = None


class ContractDiffObservedInput(_In):
    language: Optional[str] = Field(default=None, description=_LANGUAGE_HELP)


class ContractDiffObservedOutput(BaseModel):
    report: dict[str, Any]
    corpus_size: int
    clean: bool = Field(
        description="True only when the corpus is non-empty AND nothing "
        "undocumented appeared. An empty corpus is never clean — it proves "
        "nothing."
    )
    next_step: str


# ── diagnostics ───────────────────────────────────────────────────────


class DiagnosticsConnectionStatusInput(_In):
    pass


class DiagnosticsConnectionStatusOutput(BaseModel):
    ok: bool
    api_configured: bool
    receiver_configured: bool
    base_url: Optional[str] = None
    region: str
    sandbox: bool
    sandbox_window: Optional[str] = None
    receiver_url: Optional[str] = None
    receiver_url_problems: list[str] = Field(
        default_factory=list,
        description="Reasons the configured receiver URL must not be "
        "registered with the live vendor.",
    )
    has_client_id: bool
    has_client_secret: bool
    has_webhook_secret: bool
    contract_verified: bool
    next_step: Optional[str] = None


class DiagnosticsProbeInput(_In):
    pass


class DiagnosticsProbeOutput(BaseModel):
    results: list[dict[str, Any]]
    unexpected: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rows whose observed status contradicts a RECORDED "
        "expectation. Read this, not `results`.",
    )
    unverified: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rows with no recorded expectation — every row until "
        "Gate 1. Their observed status is what fills the baseline in.",
    )
    caveat: str = Field(
        description="Why most rows here cannot settle anything on their own."
    )
    probed: bool


class DiagnosticsListKnownEndpointsInput(_In):
    pass


class DiagnosticsListKnownEndpointsOutput(BaseModel):
    endpoints: list[dict[str, Any]]
    path_variants: dict[str, list[str]] = Field(
        description="Paths whose spelling the generated spec and the "
        "hand-written docs disagree on. Spec spelling first."
    )
    login_button_urls: dict[str, str]
    reference_urls: dict[str, str]
    support_contacts: dict[str, str]
    sandbox_window: str


class DiagnosticsFetchSwaggerInput(_In):
    include_paths: bool = Field(
        default=False,
        description="Include the full path list from each host. Large — the "
        "diff against our baseline is usually what you want.",
    )


class DiagnosticsFetchSwaggerOutput(BaseModel):
    hosts: dict[str, Any] = Field(
        description="Per host: url, http status, spec version, path count, "
        "and any transport error."
    )
    in_spec_not_in_baseline: list[str] = Field(
        default_factory=list,
        description="Endpoints the vendor serves that we have not written "
        "down — capability we may be missing.",
    )
    in_baseline_not_in_spec: list[str] = Field(
        default_factory=list,
        description="Endpoints we believe in that the spec does not list. "
        "Either a transcription error or a path spelled differently.",
    )
    confirmed: list[str] = Field(default_factory=list)
    sandbox_only: list[str] = Field(
        default_factory=list,
        description="Present on sandbox, absent on prod — the event "
        "simulator lives here.",
    )
    prod_only: list[str] = Field(default_factory=list)
    paths: Optional[dict[str, list[str]]] = None
    next_step: str


# ── callbacks ─────────────────────────────────────────────────────────


class CallbacksGetConfigInput(_In):
    pass


class CallbacksGetConfigOutput(BaseModel):
    fetched: bool
    config: Optional[dict[str, Any]] = Field(
        default=None,
        description="The registered configuration. `authorizationHeaderValue` "
        "is redacted — it is the entire inbound security boundary.",
    )
    subscriptions: list[str] = Field(default_factory=list)
    delivers_nothing: bool = Field(
        default=False,
        description="True when no events are subscribed. The vendor accepts "
        "this and then delivers nothing, silently — the likeliest production "
        "failure and the one with no error anywhere.",
    )
    receiver_url_matches: Optional[bool] = Field(
        default=None,
        description="Whether the registered URL equals IMOVELWEB_RECEIVER_URL. "
        "False means leads are going somewhere else.",
    )
    problems: list[str] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


class CallbacksPutConfigInput(_In):
    url: Optional[str] = Field(
        default=None,
        description="Receiver URL to register. Defaults to "
        "IMOVELWEB_RECEIVER_URL.",
    )
    language: Optional[str] = Field(default=None, description=_LANGUAGE_HELP)
    subscriptions: Optional[list[str]] = Field(
        default=None,
        description="Events to subscribe. Defaults to CONTACTO + "
        "CONTACTO_MENSAJE. An empty list is refused.",
    )
    authorization_header_key: Optional[str] = Field(
        default=None, description="Defaults to Authorization."
    )
    allow_local_url: bool = Field(
        default=False,
        description="Permit a localhost / private / tunnel URL. Only ever "
        "correct against a Fake or a sandbox rehearsal — against the live "
        "vendor it blackholes every agency's leads with no error.",
    )
    confirm: bool = Field(
        default=False,
        description="Must be true. This write is INTEGRATOR-WIDE — there is "
        "no agency in the path, so it redirects every agency's leads at once.",
    )


class CallbacksPutConfigOutput(BaseModel):
    registered: bool
    requested: Optional[dict[str, Any]] = None
    previous: Optional[dict[str, Any]] = Field(
        default=None,
        description="What was registered BEFORE this call. Kept because "
        "after a bad PUT the vendor cannot tell you what you had.",
    )
    applied: Optional[dict[str, Any]] = Field(
        default=None, description="What the vendor reports AFTER the write."
    )
    drift: list[str] = Field(
        default_factory=list,
        description="Differences between requested and applied. A PUT that "
        "silently drops `subscriptions` is otherwise invisible.",
    )
    warnings: list[str] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


class CallbacksSubscribeInput(_In):
    event: str = Field(description="CONTACTO | CONTACTO_MENSAJE | AVISO_* | CREDITO.")
    confirm: bool = Field(default=False, description="Must be true — integrator-wide.")


class CallbacksSubscribeOutput(BaseModel):
    subscribed: bool
    event: Optional[str] = None
    subscriptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


class CallbacksUnsubscribeInput(_In):
    event: str
    confirm: bool = Field(default=False, description="Must be true — integrator-wide.")


class CallbacksUnsubscribeOutput(BaseModel):
    unsubscribed: bool
    event: Optional[str] = None
    subscriptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


# ── agencies ──────────────────────────────────────────────────────────


class AgenciesListInput(_In):
    page: int = Field(default=0, ge=0)
    size: int = Field(default=100, ge=1, le=500)


class AgenciesListOutput(BaseModel):
    listed: bool
    agencies: list[dict[str, Any]] = Field(default_factory=list)
    page: int = 0
    size: int = 0
    total: Optional[int] = None
    note: Optional[str] = Field(
        default=None,
        description="These agency codes are the tenant-resolution key: WE "
        "choose them at onboarding, which is what makes org resolution a "
        "pure lookup instead of a guess.",
    )
    error: Optional[dict[str, Any]] = None


# ── leads (the pull side) ─────────────────────────────────────────────


class _PiiIn(_In):
    include_pii: bool = Field(
        default=False,
        description="Return national identifiers (CPF) unredacted. Default "
        "false: an MCP result goes into a model's context window, and LGPD "
        "minimization (Art. 6.III) says we do not surface what no feature "
        "uses.",
    )


class LeadsGetMessageInput(_PiiIn):
    id_mensaje: int = Field(description="The vendor's message id.")


class LeadsGetMessageOutput(BaseModel):
    fetched: bool
    message: Optional[dict[str, Any]] = None
    pii_redacted: int = 0
    error: Optional[dict[str, Any]] = None


class LeadsListMessagesInput(_PiiIn):
    codigo_imobiliaria: str = Field(description="The agency code.")
    from_date: str = Field(description="yyyyMMdd. Required by the vendor.")
    to_date: Optional[str] = None
    page: int = Field(default=0, ge=0)
    size: int = Field(default=100, ge=1, le=500)


class LeadsListMessagesOutput(BaseModel):
    fetched: bool
    messages: list[dict[str, Any]] = Field(default_factory=list)
    page: int = 0
    size: int = 0
    total: Optional[int] = None
    pii_redacted: int = 0
    caveat: Optional[str] = Field(
        default=None,
        description="A reconcile row carries no eventId, so it cannot be "
        "deduplicated against a callback delivery by id alone.",
    )
    error: Optional[dict[str, Any]] = None


class LeadsGetSmartleadInput(_PiiIn):
    id_mensagem: int


class LeadsGetSmartleadOutput(BaseModel):
    fetched: bool
    smartlead: Optional[dict[str, Any]] = None
    pii_redacted: int = 0
    lgpd_note: str = Field(
        default="",
        description="Smartlead is behavioural profiling of an identified "
        "person. If leads are ever scored or routed on it, LGPD Art. 20 "
        "(right to review of automated decisions) engages.",
    )
    error: Optional[dict[str, Any]] = None


class LeadsListContactActionsInput(_In):
    pass


class LeadsListContactActionsOutput(BaseModel):
    fetched: bool
    actions: list[dict[str, Any]] = Field(default_factory=list)
    transcribed: dict[str, str] = Field(
        default_factory=dict,
        description="Our current hand-transcribed contactTypeId catalog.",
    )
    divergence: list[str] = Field(
        default_factory=list,
        description="Where the live catalog and our transcription disagree. "
        "This is what closes Gate 1.11.",
    )
    error: Optional[dict[str, Any]] = None


# ── sandbox ───────────────────────────────────────────────────────────


class SandboxEmitEventInput(_In):
    event_type: str = Field(
        default="CONTACTO_MENSAJE",
        description="CONTACTO | CONTACTO_MENSAJE | AVISO_* | CREDITO. "
        "CONTACTO_MENSAJE needs name + phone + email + message; CONTACTO "
        "needs only an email.",
    )
    codigo_imobiliaria: str = Field(description="Must be REAL in the sandbox.")
    codigo_aviso: Optional[str] = Field(
        default=None, description="Listing code. Must be REAL in the sandbox."
    )
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_message: Optional[str] = None
    referer: Optional[str] = None
    confirm: bool = Field(
        default=False,
        description="Must be true — this asks the vendor to push a real "
        "delivery at our registered receiver.",
    )


class SandboxEmitEventOutput(BaseModel):
    emitted: bool
    base_url: Optional[str] = None
    sandbox_window: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    response: Optional[dict[str, Any]] = None
    next_step: Optional[str] = None
    error: Optional[dict[str, Any]] = None


# ── webhook (our own receiver) ────────────────────────────────────────


class WebhookRecordDeliveryInput(_In):
    payload: dict[str, Any] = Field(
        description="A REAL inbound body to add to the observed corpus."
    )
    label: Optional[str] = Field(
        default=None, description="Optional note, e.g. 'first sandbox delivery'."
    )
    language: Optional[str] = Field(default=None, description=_LANGUAGE_HELP)
    confirm: bool = Field(default=False, description="Must be true — writes a file.")


class WebhookRecordDeliveryOutput(BaseModel):
    recorded: bool
    path: Optional[str] = None
    event_id: Optional[str] = None
    detected_language: Optional[str] = None
    corpus_size: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


class WebhookSimulateInput(_In):
    language: Optional[str] = Field(default=None, description=_LANGUAGE_HELP)
    event_type: str = Field(default="CONTACTO_MENSAJE")
    event_id: Optional[str] = Field(
        default=None, description="Override the id — reuse one to test idempotency."
    )
    wrong_secret: bool = Field(
        default=False,
        description="Send a deliberately wrong credential to prove the "
        "receiver 401s. Rehearsing the reject path is half the point.",
    )
    confirm: bool = Field(default=False, description="Must be true — this POSTs.")


class WebhookSimulateOutput(BaseModel):
    sent: bool
    receiver_url: Optional[str] = None
    http_status: Optional[int] = None
    latency_ms: Optional[float] = None
    response_budget_ms: float = Field(
        default=1500.0,
        description="The vendor's hard limit. A slower answer is scored an "
        "error and starts the 72-hour retry loop.",
    )
    within_response_budget: Optional[bool] = None
    interpretation: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


__all__ = [
    "AgenciesListInput", "AgenciesListOutput",
    "CallbacksGetConfigInput", "CallbacksGetConfigOutput",
    "CallbacksPutConfigInput", "CallbacksPutConfigOutput",
    "CallbacksSubscribeInput", "CallbacksSubscribeOutput",
    "CallbacksUnsubscribeInput", "CallbacksUnsubscribeOutput",
    "ContractDescribeInput", "ContractDescribeOutput",
    "ContractDiffObservedInput", "ContractDiffObservedOutput",
    "ContractValidatePayloadInput", "ContractValidatePayloadOutput",
    "DiagnosticsConnectionStatusInput", "DiagnosticsConnectionStatusOutput",
    "DiagnosticsFetchSwaggerInput", "DiagnosticsFetchSwaggerOutput",
    "DiagnosticsListKnownEndpointsInput", "DiagnosticsListKnownEndpointsOutput",
    "DiagnosticsProbeInput", "DiagnosticsProbeOutput",
    "LeadsGetMessageInput", "LeadsGetMessageOutput",
    "LeadsGetSmartleadInput", "LeadsGetSmartleadOutput",
    "LeadsListContactActionsInput", "LeadsListContactActionsOutput",
    "LeadsListMessagesInput", "LeadsListMessagesOutput",
    "SandboxEmitEventInput", "SandboxEmitEventOutput",
    "WebhookRecordDeliveryInput", "WebhookRecordDeliveryOutput",
    "WebhookSimulateInput", "WebhookSimulateOutput",
]
