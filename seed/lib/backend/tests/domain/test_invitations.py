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
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.invitations import accept_invitation
from noctusai_lib.testing.mocks import MockSupabaseClient


@pytest.fixture
def mock_db():
    db = MockSupabaseClient(validate_schema=False, schema="test")
    db.set_table_data(
        "test.invitations",
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
        accept_invitation(mock_db, "test.invitations", "inv-1")

        payloads = mock_db.table("test.invitations").updated_payloads
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
            mock_db, "test.invitations", "inv-1", accepted_by=None
        )

        payloads = mock_db.table("test.invitations").updated_payloads
        assert len(payloads) == 1
        assert payloads[0] == {"status": "accepted"}


class TestAcceptInvitationWithAcceptedBy:
    """When `accepted_by` is passed, the UPDATE payload includes
    `accepted_at` (utcnow ISO8601) + `accepted_by`.
    """

    def test_accept_with_accepted_by_writes_three_fields(self, mock_db):
        accept_invitation(
            mock_db,
            "test.invitations",
            "inv-1",
            accepted_by="u-invitee",
        )

        payloads = mock_db.table("test.invitations").updated_payloads
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
            "test.invitations",
            "inv-1",
            accepted_by="u-invitee",
        )
        after = datetime.now(timezone.utc)

        payload = mock_db.table("test.invitations").updated_payloads[0]
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
                mock_db, "test.invitations", "inv-1", "u-invitee"
            )
