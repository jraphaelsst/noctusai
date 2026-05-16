"""HTTP surface for the social-wiring ``scheduling`` module.

Absorbed real-estate scheduling domain (Wave 2.3). Exposes:

  - CRUD-lite over the scheduling reference data (condominiums /
    properties / services / scheduling users) — RLS-bounded by the
    user-scoped Supabase client.
  - Appointment + appointment-request reads.
  - Pending-chat-identity admin resolve (LID deferred-auth surface).
  - ``POST /api/scheduling/propose`` — drives the seed
    ``SchedulingEngine`` via ``SchedulingService`` to return candidate
    slots (read-only; no DB write).

Auth pattern: ``Depends(get_current_user_org)`` per
``KB § PATTERNS/backend.md § Auth — canonical pattern``. All reads go
through the RLS-bounded user client; the engine-backed ``propose`` uses
the admin client (single-agency org scoping in-service) so the slot
generation sees confirmed bookings.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_user_client,
)
from app.modules.scheduling.engine import (
    DEFAULT_RULE_CONFIG,
    SchedulingService,
    build_rules,
)
from app.modules.scheduling.schemas import (
    AppointmentOut,
    AppointmentRequestOut,
    CondominiumCreate,
    CondominiumOut,
    CondominiumUpdate,
    PendingChatIdentityOut,
    PendingChatIdentityResolve,
    ProposedSlotOut,
    ProposeRequest,
    ProposeResponse,
    PropertyCreate,
    PropertyOut,
    PropertyUpdate,
    ServiceCreate,
    ServiceOut,
    UserCreate,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduling", tags=["scheduling"])

_SCHEMA = "social_wiring"


def _scoped(token: str):
    """RLS-bounded scheduling-schema handle from the user JWT."""
    return get_user_client(token).schema(_SCHEMA)


# ---------------------------------------------------------------------------
# Condominiums
# ---------------------------------------------------------------------------


@router.get("/condominiums", response_model=list[CondominiumOut])
def list_condominiums(
    auth: tuple = Depends(get_current_user_org),
) -> list[CondominiumOut]:
    _user, token, _raw_org = auth
    resp = _scoped(token).table("sched_condominiums").select("*").execute()
    return [CondominiumOut(**row) for row in (resp.data or [])]


@router.post(
    "/condominiums",
    response_model=CondominiumOut,
    status_code=status.HTTP_201_CREATED,
)
def create_condominium(
    payload: CondominiumCreate,
    auth: tuple = Depends(get_current_user_org),
) -> CondominiumOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    body = payload.model_dump()
    body["org_id"] = str(org_id)
    resp = _scoped(token).table("sched_condominiums").insert(body).execute()
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="condominium insert returned no row",
        )
    return CondominiumOut(**rows[0])


@router.patch("/condominiums/{condominium_id}", response_model=CondominiumOut)
def update_condominium(
    condominium_id: UUID,
    payload: CondominiumUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> CondominiumOut:
    _user, token, _raw_org = auth
    body = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields to update",
        )
    resp = (
        _scoped(token)
        .table("sched_condominiums")
        .update(body)
        .eq("id", str(condominium_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"condominium {condominium_id} not found",
        )
    return CondominiumOut(**rows[0])


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@router.get("/properties", response_model=list[PropertyOut])
def list_properties(
    auth: tuple = Depends(get_current_user_org),
) -> list[PropertyOut]:
    _user, token, _raw_org = auth
    resp = _scoped(token).table("sched_properties").select("*").execute()
    return [PropertyOut(**row) for row in (resp.data or [])]


@router.post(
    "/properties",
    response_model=PropertyOut,
    status_code=status.HTTP_201_CREATED,
)
def create_property(
    payload: PropertyCreate,
    auth: tuple = Depends(get_current_user_org),
) -> PropertyOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    body = payload.model_dump(mode="json")
    body["org_id"] = str(org_id)
    resp = _scoped(token).table("sched_properties").insert(body).execute()
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="property insert returned no row",
        )
    return PropertyOut(**rows[0])


@router.patch("/properties/{property_id}", response_model=PropertyOut)
def update_property(
    property_id: UUID,
    payload: PropertyUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> PropertyOut:
    _user, token, _raw_org = auth
    body = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields to update",
        )
    resp = (
        _scoped(token)
        .table("sched_properties")
        .update(body)
        .eq("id", str(property_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"property {property_id} not found",
        )
    return PropertyOut(**rows[0])


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


@router.get("/services", response_model=list[ServiceOut])
def list_services(
    auth: tuple = Depends(get_current_user_org),
) -> list[ServiceOut]:
    _user, token, _raw_org = auth
    resp = _scoped(token).table("sched_services").select("*").execute()
    return [ServiceOut(**row) for row in (resp.data or [])]


@router.post(
    "/services",
    response_model=ServiceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_service(
    payload: ServiceCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ServiceOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    body = payload.model_dump()
    body["org_id"] = str(org_id)
    resp = _scoped(token).table("sched_services").insert(body).execute()
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="service insert returned no row",
        )
    return ServiceOut(**rows[0])


# ---------------------------------------------------------------------------
# Scheduling users (agency staff + media crew)
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserOut])
def list_users(
    auth: tuple = Depends(get_current_user_org),
) -> list[UserOut]:
    _user, token, _raw_org = auth
    resp = _scoped(token).table("sched_users").select("*").execute()
    return [UserOut(**row) for row in (resp.data or [])]


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    auth: tuple = Depends(get_current_user_org),
) -> UserOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    body = payload.model_dump()
    body["org_id"] = str(org_id)
    resp = _scoped(token).table("sched_users").insert(body).execute()
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user insert returned no row",
        )
    return UserOut(**rows[0])


# ---------------------------------------------------------------------------
# Appointments + requests (reads)
# ---------------------------------------------------------------------------


@router.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(
    appointment_status: str | None = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
) -> list[AppointmentOut]:
    _user, token, _raw_org = auth
    query = _scoped(token).table("sched_appointments").select("*")
    if appointment_status:
        query = query.eq("status", appointment_status)
    resp = query.execute()
    return [AppointmentOut(**row) for row in (resp.data or [])]


@router.get("/appointment-requests", response_model=list[AppointmentRequestOut])
def list_appointment_requests(
    auth: tuple = Depends(get_current_user_org),
) -> list[AppointmentRequestOut]:
    _user, token, _raw_org = auth
    resp = (
        _scoped(token)
        .table("sched_appointment_requests")
        .select("*")
        .execute()
    )
    return [AppointmentRequestOut(**row) for row in (resp.data or [])]


# ---------------------------------------------------------------------------
# Pending chat identities (LID deferred-auth admin)
# ---------------------------------------------------------------------------


@router.get("/pending-chat-identities", response_model=list[PendingChatIdentityOut])
def list_pending_chat_identities(
    auth: tuple = Depends(get_current_user_org),
) -> list[PendingChatIdentityOut]:
    _user, token, _raw_org = auth
    resp = (
        _scoped(token)
        .table("sched_pending_chat_identities")
        .select("*")
        .execute()
    )
    return [PendingChatIdentityOut(**row) for row in (resp.data or [])]


@router.patch(
    "/pending-chat-identities/{identity_id}",
    response_model=PendingChatIdentityOut,
)
def resolve_pending_chat_identity(
    identity_id: UUID,
    payload: PendingChatIdentityResolve,
    auth: tuple = Depends(get_current_user_org),
) -> PendingChatIdentityOut:
    """Resolve / reject a parked LID. When ``resolved_to_user_id`` is set
    the caller is expected to also update that user's
    ``linked_identity`` so future inbounds hit the fast LID path — that
    write is left to the admin UI flow (single-responsibility endpoint)."""
    _user, token, _raw_org = auth
    body: dict[str, Any] = {"status": payload.status}
    if payload.resolved_to_user_id is not None:
        body["resolved_to_user_id"] = str(payload.resolved_to_user_id)
    resp = (
        _scoped(token)
        .table("sched_pending_chat_identities")
        .update(body)
        .eq("id", str(identity_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"pending chat identity {identity_id} not found",
        )
    return PendingChatIdentityOut(**rows[0])


# ---------------------------------------------------------------------------
# Engine-backed propose (read-only slot generation)
# ---------------------------------------------------------------------------


@router.post("/propose", response_model=ProposeResponse)
def propose_slots(
    payload: ProposeRequest,
    auth: tuple = Depends(get_current_user_org),
) -> ProposeResponse:
    """Drive the seed ``SchedulingEngine`` for candidate slots. Read-only
    — no appointment is created. Confirmation is a chat-layer / tool
    operation (``confirm_appointment``)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = SchedulingService(
        get_admin_client(),
        org_id=org_id,
        rules=build_rules(DEFAULT_RULE_CONFIG),
    )
    try:
        proposed = service.propose_appointment(
            property_code=payload.property_code,
            requested_date=payload.requested_date,
            time_window=payload.time_window,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return ProposeResponse(
        property_code=payload.property_code,
        slots=[
            ProposedSlotOut(
                start_at=s.start_at,
                end_at=s.end_at,
                duration_minutes=s.duration_minutes,
                score=s.score,
            )
            for s in proposed
        ],
    )


__all__ = ["router"]
