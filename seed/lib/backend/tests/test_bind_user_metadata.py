"""
Tests for ``noctusai_lib.testing.bind_user_metadata``.

Lifted into seed-lib during ``adconnect-test-conftest-distributor-binding``
Phase 2 from N=15+ inline ``mock.auth.get_user = MagicMock(return_value=
MockUserResponse(MockUser(...)))`` callsites across product conftests.
"""
from __future__ import annotations

from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_user_metadata,
)


class TestBindUserMetadata:
    def test_returns_mock_user_response_with_role(self) -> None:
        mock_sb = MockSupabaseClient()
        response = bind_user_metadata(mock_sb, role="admin", org_id="org-1")
        assert isinstance(response, MockUserResponse)
        assert response.user.user_metadata["role"] == "admin"
        assert response.user.user_metadata["org_id"] == "org-1"

    def test_rebinds_auth_get_user(self) -> None:
        """The mock's `auth.get_user` must yield the new user regardless of
        token bytes — that's the contract callers depend on."""
        mock_sb = MockSupabaseClient()
        bind_user_metadata(mock_sb, role="customer", org_id="org-2")
        # Token argument is ignored by the MagicMock binding.
        result = mock_sb.auth.get_user("any-token-bytes")
        assert result.user.user_metadata["role"] == "customer"
        assert result.user.user_metadata["org_id"] == "org-2"

    def test_accepts_authclient_via_mock_supabase_attr(self) -> None:
        """`AuthClient` exposes `.mock_supabase` — the helper unwraps it
        transparently so callers don't need an extra dereference step."""
        mock_sb = MockSupabaseClient()

        class FakeAuthClient:
            mock_supabase = mock_sb

        ac = FakeAuthClient()
        bind_user_metadata(ac, role="owner", org_id="org-3")
        result = mock_sb.auth.get_user("ignored")
        assert result.user.user_metadata["role"] == "owner"

    def test_accepts_prebuilt_mock_user(self) -> None:
        """When `user=` is passed, all MockUser-shaping kwargs are ignored."""
        mock_sb = MockSupabaseClient()
        custom = MockUser(id="custom-id", role="therapist", clinic_id="c-9")
        response = bind_user_metadata(mock_sb, user=custom, role="should-be-ignored")
        assert response.user is custom
        assert response.user.user_metadata["role"] == "therapist"
        assert response.user.user_metadata["clinic_id"] == "c-9"

    def test_extra_metadata_propagates(self) -> None:
        """Product-specific extra metadata (e.g. AdConnect's distributor_id)
        must round-trip through `extra_metadata`."""
        mock_sb = MockSupabaseClient()
        bind_user_metadata(
            mock_sb,
            role="customer",
            org_id="org-x",
            extra_metadata={"distributor_id": "dist-001"},
        )
        result = mock_sb.auth.get_user("ignored")
        assert result.user.user_metadata["distributor_id"] == "dist-001"

    def test_omitted_kwargs_omitted_from_metadata(self) -> None:
        """When `org_id` (or `role`, etc.) is None, it must NOT land in
        `user_metadata` (would otherwise mask absence)."""
        mock_sb = MockSupabaseClient()
        bind_user_metadata(mock_sb, role="admin")  # no org_id
        result = mock_sb.auth.get_user("ignored")
        assert "org_id" not in result.user.user_metadata
        assert result.user.user_metadata["role"] == "admin"
