"""Tests for the absorbed LID-aware authorization service (Wave 2.3)."""
from __future__ import annotations

from uuid import UUID, uuid4

from noctusai_lib.testing import MockSupabaseClient
from app.modules.scheduling.authorization import (
    AuthorizationService,
    looks_like_lid,
    normalize_phone_number,
)

_ORG = UUID("00000000-0000-4000-8000-000000000001")


def test_normalize_phone_number_variants():
    assert normalize_phone_number("+55 (11) 99999-9999") == "+5511999999999"
    assert normalize_phone_number("5511999999999") == "+5511999999999"
    assert normalize_phone_number(None) == ""
    assert normalize_phone_number("abc") == ""


def test_looks_like_lid_shapes():
    assert looks_like_lid("12345@lid_abcdef") is True
    assert looks_like_lid("12345@lid") is True
    assert looks_like_lid("5511999999999@c.us") is False
    assert looks_like_lid(None) is False


def _svc(rows: list[dict]) -> AuthorizationService:
    return AuthorizationService(
        MockSupabaseClient(rows, validate_schema=False), org_id=_ORG
    )


def test_authorize_inbound_phone_path_match():
    uid = str(uuid4())
    rows = [
        {
            "id": uid,
            "role": "real_estate_agent",
            "phone_number": "+5511999999999",
            "linked_identity": None,
            "active": True,
            "org_id": str(_ORG),
        }
    ]
    result = _svc(rows).authorize_inbound(
        chat_id="5511999999999@c.us",
        from_phone="+5511999999999",
    )
    assert result.authorized is True
    assert str(result.user_id) == uid
    assert result.role == "real_estate_agent"


def test_authorize_inbound_lid_path_match():
    uid = str(uuid4())
    rows = [
        {
            "id": uid,
            "role": "media_crew",
            "phone_number": "+5511888888888",
            "linked_identity": "777@lid_deadbeef",
            "active": True,
            "org_id": str(_ORG),
        }
    ]
    result = _svc(rows).authorize_inbound(chat_id="777@lid_deadbeef")
    assert result.authorized is True
    assert str(result.user_id) == uid
    assert result.lid == "777@lid_deadbeef"


def test_authorize_inbound_unauthorized_surfaces_lid_for_parking():
    result = _svc([]).authorize_inbound(chat_id="999@lid_cafe")
    assert result.authorized is False
    assert result.user_id is None
    assert result.lid == "999@lid_cafe"


def test_park_pending_lid_inserts_row():
    svc = _svc([])
    row = svc.park_pending_lid(
        "999@lid_cafe", push_name="Visitor", phone_hint="+5511"
    )
    # Returns the inserted payload (or the prepared payload on UNIQUE race).
    assert row["chat_id"] == "999@lid_cafe"
    assert row["status"] == "pending"
    assert row["org_id"] == str(_ORG)
