"""
Structural tests for the Phase 3 Pydantic schemas.

Verifies that each domain entity's ``Create`` / ``Update`` / ``Out``
schemas accept canonical-shape payloads and reject obvious bad inputs
(end-before-start appointments, empty strings on required fields,
out-of-range coordinates, etc.). Mirrors the validation invariants
encoded in the migration's CHECK constraints.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRequestCreate,
    AppointmentRequestStatus,
    AppointmentStatus,
    AppointmentUpdate,
)
from app.schemas.condominium import CondominiumCreate
from app.schemas.conversation import (
    ConversationMessageCreate,
    ConversationSummaryCreate,
)
from app.schemas.oauth_credential import OAuthCredentialCreate
from app.schemas.pending_chat_identity import (
    PendingChatIdentityCreate,
    PendingChatIdentityResolve,
)
from app.schemas.property import PropertyCreate
from app.schemas.route import RouteCacheUpsert, RouteGroupCreate
from app.schemas.service import CrewSkillCreate, ServiceCreate
from app.schemas.user import UserCreate, UserRole

NOW = datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["real_estate_agent", "media_crew", "admin"])
def test_user_create_accepts_canonical_roles(role: UserRole) -> None:
    user = UserCreate(name="Alice", role=role, phone_number="+5511999990000")
    assert user.role == role
    assert user.active is True  # default


def test_user_create_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        UserCreate(name="Alice", role="janitor", phone_number="+5511999990000")  # type: ignore[arg-type]


def test_user_create_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        UserCreate(name="", role="admin", phone_number="+5511999990000")


# ---------------------------------------------------------------------------
# Condominiums
# ---------------------------------------------------------------------------


def test_condominium_create_accepts_valid_coords() -> None:
    cond = CondominiumCreate(
        name="Edifício Aurora",
        address="Av. Paulista, 1000",
        latitude=-23.561,
        longitude=-46.656,
    )
    assert cond.latitude == pytest.approx(-23.561)


def test_condominium_create_rejects_out_of_range_latitude() -> None:
    with pytest.raises(ValidationError):
        CondominiumCreate(
            name="X",
            address="Y",
            latitude=120.0,
            longitude=0.0,
        )


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_property_create_accepts_canonical() -> None:
    prop = PropertyCreate(condominium_id=uuid4(), code="APT-12B", unit="12B")
    assert prop.code == "APT-12B"


def test_property_create_rejects_empty_code() -> None:
    with pytest.raises(ValidationError):
        PropertyCreate(condominium_id=uuid4(), code="")


# ---------------------------------------------------------------------------
# Services + Crew skills
# ---------------------------------------------------------------------------


def test_service_create_default_duration_thirty_minutes() -> None:
    svc = ServiceCreate(name="Foto interna")
    assert svc.default_duration_minutes == 30


def test_service_create_rejects_zero_duration() -> None:
    with pytest.raises(ValidationError):
        ServiceCreate(name="Foto", default_duration_minutes=0)


def test_crew_skill_create_canonical() -> None:
    skill = CrewSkillCreate(user_id=uuid4(), service_id=uuid4())
    assert skill.user_id != skill.service_id


# ---------------------------------------------------------------------------
# Appointment lifecycle
# ---------------------------------------------------------------------------


def test_appointment_request_create_default_status() -> None:
    req = AppointmentRequestCreate(requester_user_id=uuid4())
    assert req.status == "collecting_details"


@pytest.mark.parametrize(
    "status",
    [
        "collecting_details",
        "pending_confirmation",
        "confirmed",
        "cancelled",
        "expired",
    ],
)
def test_appointment_request_status_accepts_canonical(
    status: AppointmentRequestStatus,
) -> None:
    req = AppointmentRequestCreate(requester_user_id=uuid4(), status=status)
    assert req.status == status


def test_appointment_create_requires_end_after_start() -> None:
    start = NOW
    with pytest.raises(ValidationError):
        AppointmentCreate(
            property_id=uuid4(),
            condominium_id=uuid4(),
            start_at=start,
            end_at=start,  # not strictly greater → invalid
        )
    with pytest.raises(ValidationError):
        AppointmentCreate(
            property_id=uuid4(),
            condominium_id=uuid4(),
            start_at=start,
            end_at=start - timedelta(minutes=1),
        )


def test_appointment_create_canonical_window() -> None:
    appt = AppointmentCreate(
        property_id=uuid4(),
        condominium_id=uuid4(),
        start_at=NOW,
        end_at=NOW + timedelta(minutes=30),
    )
    assert appt.status == "scheduled"


@pytest.mark.parametrize(
    "status",
    ["scheduled", "completed", "cancelled", "no_show", "rescheduled"],
)
def test_appointment_status_accepts_canonical(status: AppointmentStatus) -> None:
    appt = AppointmentCreate(
        property_id=uuid4(),
        condominium_id=uuid4(),
        start_at=NOW,
        end_at=NOW + timedelta(hours=1),
        status=status,
    )
    assert appt.status == status


def test_appointment_update_partial_skips_window_check_when_one_side_missing() -> None:
    # Only start_at provided — validator must NOT raise (no comparison to make).
    upd = AppointmentUpdate(start_at=NOW)
    assert upd.end_at is None


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


def test_conversation_message_create_inbound() -> None:
    msg = ConversationMessageCreate(
        provider_message_id="WAHA-abc-123",
        direction="inbound",
        message_text="Olá, gostaria de agendar visita",
    )
    assert msg.direction == "inbound"


def test_conversation_message_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        ConversationMessageCreate(
            direction="inbound",
            message_text="",
        )


def test_conversation_summary_create_canonical() -> None:
    summary = ConversationSummaryCreate(
        conversation_id="conv-xyz",
        summary_text="User scheduled a photo session for Tuesday.",
        ended_at=NOW,
        message_count=12,
    )
    assert summary.message_count == 12


# ---------------------------------------------------------------------------
# Pending chat identity
# ---------------------------------------------------------------------------


def test_pending_chat_identity_canonical() -> None:
    pending = PendingChatIdentityCreate(
        chat_id="@lid_1234567890",
        push_name="Joana",
        phone_hint="+5511",
    )
    assert pending.status == "pending"


def test_pending_chat_identity_resolve_canonical() -> None:
    resolved = PendingChatIdentityResolve(
        status="resolved",
        resolved_to_user_id=uuid4(),
    )
    assert resolved.status == "resolved"


# ---------------------------------------------------------------------------
# OAuth credential
# ---------------------------------------------------------------------------


def test_oauth_credential_create_canonical() -> None:
    cred = OAuthCredentialCreate(
        provider="google_calendar",
        account_email="bot@example.com",
        refresh_token="encrypted-blob",
        scopes="https://www.googleapis.com/auth/calendar",
    )
    assert cred.provider == "google_calendar"


def test_oauth_credential_create_rejects_empty_refresh_token() -> None:
    with pytest.raises(ValidationError):
        OAuthCredentialCreate(
            provider="google_calendar",
            account_email="bot@example.com",
            refresh_token="",
            scopes="x",
        )


# ---------------------------------------------------------------------------
# Routes + RouteGroups
# ---------------------------------------------------------------------------


def test_route_group_create_default_status() -> None:
    rg = RouteGroupCreate(date=date.today())
    assert rg.optimization_status == "not_started"


def test_route_cache_upsert_canonical() -> None:
    route = RouteCacheUpsert(
        origin_place_id="ChIJorigin",
        destination_place_id="ChIJdestination",
        distance_meters=1500,
        duration_seconds=420,
    )
    assert route.provider == "google_maps"


def test_route_cache_upsert_rejects_negative_distance() -> None:
    with pytest.raises(ValidationError):
        RouteCacheUpsert(
            origin_place_id="A",
            destination_place_id="B",
            distance_meters=-1,
        )
