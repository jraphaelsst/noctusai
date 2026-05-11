"""
Unit tests for ``app.services.authorization.AuthorizationService``.

Covers the LID-aware webhook authorization flow:
  * Phone path — `users.phone_number` lookup → authorized.
  * LID path — `users.linked_identity` lookup → authorized via the
    deferred-auth state an admin previously resolved.
  * Opportunistic LID capture — phone match + new LID writes
    `linked_identity` onto the user row.
  * Unauthorized rejection — no phone match + no LID match → return
    with `authorized=False`; lid surfaced for deferred-auth parking.
  * Pending-LID parking — `park_pending_lid` inserts into
    `pending_chat_identities`.

Service-layer tests — no HTTP, status-code-assertion-rule doesn't apply.
Patches target the Supabase boundary only (no monkey-patching of our
own code). MockSupabaseClient's write→read propagation lets us observe
inserts/updates via `inserted_payloads` / `updated_payloads`.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from noctusai_lib.testing import (
    MockSupabaseClient,
    MockSupabaseResponse,
)


# ---------------------------------------------------------------------------
# Pure helpers (no IO)
# ---------------------------------------------------------------------------

class TestNormalizePhoneNumber:
    """`normalize_phone_number` reduces raw phones to `+<digits>`."""

    def test_strips_non_digits(self):
        from app.services.authorization import normalize_phone_number

        assert normalize_phone_number("+55 (11) 99999-9999") == "+5511999999999"

    def test_returns_empty_for_no_digits(self):
        from app.services.authorization import normalize_phone_number

        assert normalize_phone_number("") == ""
        assert normalize_phone_number(None) == ""
        assert normalize_phone_number("abc") == ""

    def test_prepends_plus(self):
        from app.services.authorization import normalize_phone_number

        assert normalize_phone_number("5511999999999") == "+5511999999999"

    def test_handles_at_c_us_form(self):
        from app.services.authorization import normalize_phone_number

        # WAHA payloads sometimes carry `<digits>@c.us` in the from field.
        assert normalize_phone_number("5511999999999@c.us") == "+5511999999999"


class TestLooksLikeLid:
    """`looks_like_lid` recognizes both LID shapes."""

    def test_at_lid_underscore_form(self):
        from app.services.authorization import looks_like_lid

        assert looks_like_lid("5511999999999@lid_abcdef0123456789") is True

    def test_at_lid_bare_form(self):
        from app.services.authorization import looks_like_lid

        assert looks_like_lid("5511999999999@lid") is True

    def test_standard_c_us_not_a_lid(self):
        from app.services.authorization import looks_like_lid

        assert looks_like_lid("5511999999999@c.us") is False

    def test_none_or_empty(self):
        from app.services.authorization import looks_like_lid

        assert looks_like_lid(None) is False
        assert looks_like_lid("") is False


# ---------------------------------------------------------------------------
# Phone-path authorization
# ---------------------------------------------------------------------------

ORG_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "11111111-1111-1111-1111-111111111111"


def _user_row(
    *,
    user_id: str = USER_ID,
    org_id: str = ORG_ID,
    phone: str = "+5511999999999",
    role: str = "real_estate_agent",
    linked_identity: str | None = None,
    active: bool = True,
) -> dict:
    return {
        "id": user_id,
        "org_id": org_id,
        "phone_number": phone,
        "role": role,
        "linked_identity": linked_identity,
        "active": active,
    }


class TestPhoneMatch:
    """`authorize_inbound` with a standard `@c.us` chat resolves via phone."""

    def test_authorized_when_phone_matches(self):
        from app.services.authorization import AuthorizationService

        db = MockSupabaseClient(data=[_user_row()])
        svc = AuthorizationService(db, org_id=ORG_ID)

        result = svc.authorize_inbound(
            chat_id="5511999999999@c.us",
            from_phone="+5511999999999",
        )

        assert result.authorized is True
        assert result.user_id == UUID(USER_ID)
        assert result.role == "real_estate_agent"
        # `@c.us` is not a LID — lid field stays None.
        assert result.lid is None

    def test_authorized_user_id_is_a_uuid(self):
        from app.services.authorization import AuthorizationService

        db = MockSupabaseClient(data=[_user_row()])
        svc = AuthorizationService(db, org_id=ORG_ID)

        result = svc.authorize_inbound(
            chat_id="5511999999999@c.us",
            from_phone="+5511999999999",
        )

        # Critical for downstream attribution — must be UUID, not str.
        assert isinstance(result.user_id, UUID)

    def test_normalizes_phone_before_lookup(self):
        from app.services.authorization import AuthorizationService

        db = MockSupabaseClient(data=[_user_row()])
        svc = AuthorizationService(db, org_id=ORG_ID)

        # `+55 11 99999-9999` and `5511999999999@c.us` both normalize to
        # `+5511999999999` — the stored phone.
        result = svc.authorize_inbound(
            chat_id="5511999999999@c.us",
            from_phone="+55 11 99999-9999",
        )

        assert result.authorized is True

    def test_unauthorized_when_phone_does_not_match(self):
        from app.services.authorization import AuthorizationService

        # Empty users table → no match.
        db = MockSupabaseClient(data=[])
        svc = AuthorizationService(db, org_id=ORG_ID)

        result = svc.authorize_inbound(
            chat_id="5500000000000@c.us",
            from_phone="+5500000000000",
        )

        assert result.authorized is False
        assert result.user_id is None
        assert result.lid is None  # @c.us is not a LID.
        assert result.role is None


# ---------------------------------------------------------------------------
# LID-path authorization (deferred-auth resolved → user.linked_identity set)
# ---------------------------------------------------------------------------

class TestLidMatch:
    """`authorize_inbound` with a LID chat resolves via `linked_identity`."""

    def test_authorized_when_lid_matches_user(self):
        from app.services.authorization import AuthorizationService

        lid = "5511999999999@lid_abcdef0123456789"
        # Admin previously resolved a pending_chat_identity into this
        # user's `linked_identity`. Now the LID directly matches.
        db = MockSupabaseClient(data=[_user_row(linked_identity=lid)])
        svc = AuthorizationService(db, org_id=ORG_ID)

        result = svc.authorize_inbound(chat_id=lid, from_phone=None)

        assert result.authorized is True
        assert result.user_id == UUID(USER_ID)
        assert result.lid == lid
        assert result.role == "real_estate_agent"

    def test_lid_match_does_not_require_phone(self):
        """The fast-path LID lookup works without a from_phone hint."""
        from app.services.authorization import AuthorizationService

        lid = "5511999999999@lid_x"
        db = MockSupabaseClient(data=[_user_row(linked_identity=lid)])
        svc = AuthorizationService(db, org_id=ORG_ID)

        # No from_phone — must still resolve.
        result = svc.authorize_inbound(chat_id=lid, from_phone=None)
        assert result.authorized is True


class TestOpportunisticLidCapture:
    """Phone match + unseen LID writes `linked_identity` onto the user row."""

    def test_first_lid_inbound_captures_on_user(self):
        from app.services.authorization import AuthorizationService

        lid = "5511999999999@lid_freshly_seen"
        # User has no linked_identity yet — only the phone path will hit.
        # The mock's select returns the seeded `_data` unfiltered, so we
        # use `set_sequential_responses` to distinguish the two SELECTs:
        # path 1 (LID lookup) returns empty; path 2 (phone lookup)
        # returns the user; subsequent calls (the in-place update SELECT
        # of the filter builder) get an empty fallback.
        db = MockSupabaseClient(data=[])
        svc = AuthorizationService(db, org_id=ORG_ID)
        svc._scoped.set_sequential_responses(
            "users",
            [
                MockSupabaseResponse(data=[]),  # path 1: LID lookup miss
                MockSupabaseResponse(data=[_user_row(linked_identity=None)]),  # path 2: phone hit
                MockSupabaseResponse(data=[]),  # update execute (no rows to filter against)
            ],
        )

        result = svc.authorize_inbound(chat_id=lid, from_phone="+5511999999999")

        assert result.authorized is True
        assert result.user_id == UUID(USER_ID)
        assert result.lid == lid  # surfaced

        # The capture write fired against the users table on the scoped client.
        users_updates = svc._scoped.table("users").updated_payloads
        assert len(users_updates) == 1
        assert users_updates[0] == {"linked_identity": lid}

    def test_capture_not_triggered_when_chat_id_is_at_c_us(self):
        from app.services.authorization import AuthorizationService

        db = MockSupabaseClient(data=[])
        svc = AuthorizationService(db, org_id=ORG_ID)
        # Only path 2 (phone) is consulted — no LID looks-like.
        svc._scoped.set_sequential_responses(
            "users",
            [
                MockSupabaseResponse(data=[_user_row(linked_identity=None)]),  # phone match
            ],
        )

        svc.authorize_inbound(
            chat_id="5511999999999@c.us",
            from_phone="+5511999999999",
        )

        # No LID to capture → no update payload.
        users_updates = svc._scoped.table("users").updated_payloads
        assert users_updates == []

    def test_capture_not_triggered_when_lid_already_attached(self):
        from app.services.authorization import AuthorizationService

        lid = "5511999999999@lid_already_known"
        # Path 1 (LID lookup) returns the user directly — path 2 never runs.
        db = MockSupabaseClient(data=[])
        svc = AuthorizationService(db, org_id=ORG_ID)
        svc._scoped.set_sequential_responses(
            "users",
            [
                MockSupabaseResponse(data=[_user_row(linked_identity=lid)]),  # path 1 hit
            ],
        )

        result = svc.authorize_inbound(chat_id=lid, from_phone="+5511999999999")

        assert result.authorized is True
        users_updates = svc._scoped.table("users").updated_payloads
        # Path 1 (LID lookup) already resolved — no re-write.
        assert users_updates == []


# ---------------------------------------------------------------------------
# Unauthorized rejection — neither phone nor LID matches
# ---------------------------------------------------------------------------

class TestUnauthorizedRejection:
    """No phone match, no LID match → `authorized=False`."""

    def test_unknown_lid_and_unknown_phone(self):
        from app.services.authorization import AuthorizationService

        lid = "5500000000000@lid_unknown"
        db = MockSupabaseClient(data=[])
        svc = AuthorizationService(db, org_id=ORG_ID)

        result = svc.authorize_inbound(
            chat_id=lid,
            from_phone="+5500000000000",
        )

        assert result.authorized is False
        assert result.user_id is None
        # Lid surfaces so the caller can park a pending_chat_identities row.
        assert result.lid == lid
        assert result.role is None

    def test_no_chat_id_no_phone(self):
        """Empty inputs return unauthorized — no IO required."""
        from app.services.authorization import AuthorizationService

        db = MockSupabaseClient(data=[])
        svc = AuthorizationService(db, org_id=ORG_ID)

        result = svc.authorize_inbound(chat_id=None, from_phone=None)

        assert result.authorized is False
        assert result.user_id is None
        assert result.lid is None
        assert result.role is None


# ---------------------------------------------------------------------------
# park_pending_lid
# ---------------------------------------------------------------------------

class TestParkPendingLid:
    """`park_pending_lid` upserts a `pending_chat_identities` row."""

    def test_park_writes_pending_row(self):
        from app.services.authorization import AuthorizationService

        db = MockSupabaseClient(data=[])
        svc = AuthorizationService(db, org_id=ORG_ID)

        lid = "5500000000000@lid_park_me"
        svc.park_pending_lid(
            lid,
            push_name="John Doe",
            phone_hint="+5500000000000",
        )

        # The insert payload was captured on the scoped client.
        pending_inserts = svc._scoped.table("pending_chat_identities").inserted_payloads
        assert len(pending_inserts) == 1
        payload = pending_inserts[0]
        assert payload["chat_id"] == lid
        assert payload["push_name"] == "John Doe"
        assert payload["phone_hint"] == "+5500000000000"
        assert payload["status"] == "pending"
        assert payload["org_id"] == ORG_ID

    def test_park_handles_missing_metadata(self):
        from app.services.authorization import AuthorizationService

        db = MockSupabaseClient(data=[])
        svc = AuthorizationService(db, org_id=ORG_ID)

        lid = "5500000000000@lid_bare"
        svc.park_pending_lid(lid)

        pending_inserts = svc._scoped.table("pending_chat_identities").inserted_payloads
        assert len(pending_inserts) == 1
        payload = pending_inserts[0]
        assert payload["push_name"] is None
        assert payload["phone_hint"] is None
        assert payload["status"] == "pending"


# ---------------------------------------------------------------------------
# Sanity — AuthorizationResult shape
# ---------------------------------------------------------------------------

class TestAuthorizationResultShape:
    """The return value object exposes the four documented fields."""

    def test_default_fields_when_unauthorized(self):
        from app.services.authorization import AuthorizationResult

        r = AuthorizationResult(authorized=False)
        assert r.authorized is False
        assert r.user_id is None
        assert r.lid is None
        assert r.role is None

    def test_carries_all_fields_when_authorized(self):
        from app.services.authorization import AuthorizationResult

        uid = uuid4()
        r = AuthorizationResult(
            authorized=True,
            user_id=uid,
            lid="5511999999999@lid_x",
            role="admin",
        )
        assert r.authorized is True
        assert r.user_id == uid
        assert r.lid == "5511999999999@lid_x"
        assert r.role == "admin"
