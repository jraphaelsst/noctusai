"""MockSupabaseClient's implicit trusted-membership row (SEC-2, 2026-09-28).

The auth deps read org membership ONLY from `public.noctus_users`; a fixture
binding `MockUser(org_id=X)` models "a user whose trusted row says X". These
pin the three properties that keep that projection honest: it follows the
bound user, it never lifts a role out of metadata, and an explicit table
always wins (so no-row / other-row tests still prove what they claim).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from noctusai_lib.testing import MockSupabaseClient, MockUser, MockUserResponse


def _client(user=None, **kw):
    sb = MockSupabaseClient(**kw)
    if user is not None:
        sb.auth.get_user = MagicMock(return_value=MockUserResponse(user))
    return sb


def _rows(sb):
    return sb.table("noctus_users").select("org_id, org_role").eq("id", "test-user-123").limit(1).execute().data


def test_bound_user_org_is_projected_as_a_member_row():
    rows = _rows(_client(MockUser(org_id="org-a")))
    assert len(rows) == 1
    assert (rows[0]["id"], rows[0]["org_id"], rows[0]["org_role"]) == ("test-user-123", "org-a", "member")


def test_metadata_roles_are_never_lifted():
    rows = _rows(_client(MockUser(org_id="org-a", org_role="owner", noctus_role="admin")))
    assert rows[0]["org_role"] == "member"


def test_no_org_in_metadata_means_no_row():
    assert _rows(_client(MockUser())) == []


def test_unbound_auth_means_no_row():
    assert _rows(_client()) == []


def test_explicit_table_data_wins():
    sb = _client(MockUser(org_id="org-a"))
    sb.set_table_data("noctus_users", [])
    assert _rows(sb) == []


def test_rebinding_the_user_is_honoured():
    sb = _client(MockUser(org_id="org-a"))
    sb.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id="org-b")))
    assert _rows(sb)[0]["org_id"] == "org-b"


def test_schema_bound_client_still_projects():
    assert _rows(_client(MockUser(org_id="org-a"), schema="orbity"))[0]["org_id"] == "org-a"
