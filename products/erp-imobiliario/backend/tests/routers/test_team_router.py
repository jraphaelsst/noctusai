"""
Tests for Team Management router — /api/team

After the seed framework migration, the team router is provided by the
noctusai_seed framework. These tests verify the framework router is
correctly mounted and responds to basic requests.

The ERP-specific team behavior (custom roles, profile creation, etc.)
was in the old ERP team router; the framework provides a standardized
version.
"""
import pytest

# Default MockUser id is "test-user-123"
USER_ID = "test-user-123"


class TestTeamListMembers:
    def test_list_members(self, client):
        """GET /api/team -> returns 200 with data."""
        client._mock_supabase.set_table_data("noctus_users", [
            {"id": "u-1", "name": "Alice", "email": "alice@test.com",
             "org_id": "test-org-123"},
        ])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_members_empty(self, client):
        """GET /api/team -> returns 200 even with no members."""
        client._mock_supabase.set_table_data("noctus_users", [])
        resp = client.get("/api/team")
        assert resp.status_code == 200


class TestTeamInvite:
    def test_invite_no_auth(self, client):
        """POST /api/team/invite without auth -> 401."""
        resp = client.raw().post("/api/team/invite", json={
            "email": "test@test.com",
            "role": "member",
        })
        assert resp.status_code == 401


class TestTeamInvitations:
    def test_list_invitations_requires_admin(self, client):
        """GET /api/team/invitations -> 403 for non-admin users."""
        resp = client.get("/api/team/invitations")
        assert resp.status_code == 403


class TestRemoveMember:
    def test_remove_requires_admin(self, client):
        """DELETE /api/team/{user_id} -> 403 for non-admin users."""
        resp = client.delete("/api/team/some-user")
        assert resp.status_code == 403


class TestTeamValidateInvite:
    def test_validate_requires_token(self, client):
        """GET /api/team/accept/validate without token -> 422."""
        resp = client.get("/api/team/accept/validate")
        assert resp.status_code == 422
