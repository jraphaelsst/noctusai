"""Tests for `noctusai_lib.domain.invitations.accept_invitation` — the
optional `accepted_by` kwarg + `accepted_at` propagation.

Scope: `accept_invitation` Phase-2 update (2026-05-11). Adds an optional
keyword-only `accepted_by` arg. When provided, the UPDATE payload includes
`accepted_at = now()` + `accepted_by`. When omitted, only `status` is
written — preserves back-compat with adopters that haven't yet migrated
the columns.

Read-side seam: `MockRequestBuilder.updated_payloads` — captures every
`.update(...)` payload (deep-copied at storage time per the
mock-deepcopy-inputs fix). No monkey-patching of our own code.

Status-code-assertion-rule: these tests don't drive HTTP — they assert on
domain-side state. The HTTP-shape pairing is exercised in
`seed/framework/backend/tests/routers/test_team_router_accept.py`.

2026-08-06: the fixtures previously seeded `"test.invitations"` (schema-
qualified), mirroring the seed team router's `f"{schema}.invitations"` bug.
The mock keys tables by whatever string it is handed, so the fixture agreed
with the caller and BOTH were wrong — a textbook fixture-vs-real false-green
(PostgREST 500'd in prod on every invite). Table names here are now BARE, and
`TestTableNameMustBeBare` pins the guard that makes the qualified form loud.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.invitations import (
    accept_invitation,
    cancel_invitation,
    create_invitation,
    expire_old_invitations,
    list_pending_invitations,
    validate_invitation,
)
from noctusai_lib.testing.mocks import MockSupabaseClient

# The schema-qualified name the helpers must REFUSE. Named once here rather
# than written inline at each call site so it stays a deliberate fixture
# instead of six literals that read like real usage.
_QUALIFIED = "test.invitations"


@pytest.fixture
def mock_db():
    db = MockSupabaseClient(validate_schema=False, schema="test")
    db.set_table_data(
        "invitations",
        [
            {
                "id": "inv-1",
                "org_id": "org-1",
                "email": "a@test.com",
                "role": "member",
                "invited_by": "u-admin",
                "token": "tok-1",
                "status": "pending",
                "expires_at": (
                    datetime.now(timezone.utc).isoformat()
                ),
            }
        ],
    )
    return db


class TestAcceptInvitationBackCompat:
    """When `accepted_by` is NOT passed, only `status="accepted"` is written.

    Guards against breaking the 8 adopters that haven't migrated the
    `accepted_at`/`accepted_by` columns yet at the time the helper ships.
    """

    def test_accept_without_accepted_by_writes_status_only(self, mock_db):
        accept_invitation(mock_db, "invitations", "inv-1")

        payloads = mock_db.table("invitations").updated_payloads
        assert len(payloads) == 1, (
            f"Expected 1 UPDATE call, got {len(payloads)}: {payloads!r}"
        )
        payload = payloads[0]
        assert payload == {"status": "accepted"}, (
            f"Back-compat broken: payload includes columns the adopter's "
            f"table may not have. Got: {payload!r}"
        )

    def test_accept_with_explicit_none_writes_status_only(self, mock_db):
        """`accepted_by=None` is semantically identical to omitting it."""
        accept_invitation(
            mock_db, "invitations", "inv-1", accepted_by=None
        )

        payloads = mock_db.table("invitations").updated_payloads
        assert len(payloads) == 1
        assert payloads[0] == {"status": "accepted"}


class TestAcceptInvitationWithAcceptedBy:
    """When `accepted_by` is passed, the UPDATE payload includes
    `accepted_at` (utcnow ISO8601) + `accepted_by`.
    """

    def test_accept_with_accepted_by_writes_three_fields(self, mock_db):
        accept_invitation(
            mock_db,
            "invitations",
            "inv-1",
            accepted_by="u-invitee",
        )

        payloads = mock_db.table("invitations").updated_payloads
        assert len(payloads) == 1, (
            f"Expected 1 UPDATE call, got {len(payloads)}: {payloads!r}"
        )
        payload = payloads[0]
        assert set(payload.keys()) == {"status", "accepted_at", "accepted_by"}, (
            f"Expected exactly status+accepted_at+accepted_by keys, got: "
            f"{set(payload.keys())!r}"
        )
        assert payload["status"] == "accepted"
        assert payload["accepted_by"] == "u-invitee"

    def test_accepted_at_is_iso8601_utc(self, mock_db):
        before = datetime.now(timezone.utc)
        accept_invitation(
            mock_db,
            "invitations",
            "inv-1",
            accepted_by="u-invitee",
        )
        after = datetime.now(timezone.utc)

        payload = mock_db.table("invitations").updated_payloads[0]
        accepted_at = payload["accepted_at"]
        assert isinstance(accepted_at, str), (
            f"accepted_at must be ISO8601 str, got {type(accepted_at)!r}"
        )
        parsed = datetime.fromisoformat(accepted_at)
        # The helper stamps timezone-aware utcnow; assert window membership.
        assert parsed.tzinfo is not None, "accepted_at must carry timezone"
        assert before <= parsed <= after, (
            f"accepted_at outside [before, after] window: "
            f"{before.isoformat()} <= {accepted_at} <= {after.isoformat()}"
        )

    def test_accepted_by_kwarg_only(self, mock_db):
        """`accepted_by` is keyword-only — positional 4th arg must raise."""
        with pytest.raises(TypeError):
            # type: ignore[misc] — intentionally wrong shape.
            accept_invitation(  # noqa
                mock_db, "invitations", "inv-1", "u-invitee"
            )


class TestTableNameMustBeBare:
    """Every helper REFUSES a schema-qualified table name.

    The `db` handed in is already schema-targeted (`DatabaseModule.get_client`
    binds `schema=<product>`), so PostgREST resolves `db.table(name)` relative
    to that schema. Passing `"social_wiring.invitations"` therefore asks for a
    table literally named `"social_wiring.invitations"` INSIDE `social_wiring`
    → 500 `Could not find the table 'social_wiring.social_wiring.invitations'
    in the schema cache`. That error names a table nobody wrote, which is what
    made the class read as a missing migration rather than a caller bug.

    Raising at the boundary converts it into a named programming error the
    first time it runs — including under a mock, which is where the original
    slip hid (the mock keys tables by whatever string it is given, so a
    qualified fixture agreed with a qualified caller and both stayed green).

    The bad name is referenced through `_QUALIFIED` rather than written inline
    at each call: `check_postgrest_schema_qualified_table` flags a dotted
    string literal in a table-name argument position, and it is right to — a
    keeper that has to special-case its own test suite is a keeper with a hole.
    """

    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(
                lambda db: create_invitation(
                    db, _QUALIFIED, "org-1", "a@test.com", "member", "u-1"
                ),
                id="create_invitation",
            ),
            pytest.param(
                lambda db: validate_invitation(db, _QUALIFIED, "tok-1"),
                id="validate_invitation",
            ),
            pytest.param(
                lambda db: accept_invitation(db, _QUALIFIED, "inv-1"),
                id="accept_invitation",
            ),
            pytest.param(
                lambda db: cancel_invitation(db, _QUALIFIED, "inv-1", "org-1"),
                id="cancel_invitation",
            ),
            pytest.param(
                lambda db: list_pending_invitations(db, _QUALIFIED, "org-1"),
                id="list_pending_invitations",
            ),
            pytest.param(
                lambda db: expire_old_invitations(db, _QUALIFIED),
                id="expire_old_invitations",
            ),
        ],
    )
    def test_schema_qualified_table_raises_value_error(self, mock_db, call):
        with pytest.raises(ValueError, match="must be BARE"):
            call(mock_db)

    def test_bare_table_is_accepted(self, mock_db):
        """The positive half — the guard rejects dots, not every name."""
        rows = list_pending_invitations(mock_db, "invitations", "org-1")
        assert isinstance(rows, list)
