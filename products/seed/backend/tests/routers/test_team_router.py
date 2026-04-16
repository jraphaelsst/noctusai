"""
Tests for Team Management router — provided by seed framework.

These tests validate that the framework's standard team router works
correctly when consumed by the seed product.
"""
from unittest.mock import MagicMock, patch
from noctusai_shared.testing import MockSupabaseResponse


USER_ID = "test-user-123"

SAMPLE_MEMBER = {
    "id": "m1",
    "nome": "Membro Seed",
    "email": "membro@test.com",
    "org_role": "member",
    "avatar_url": None,
    "created_at": "2026-01-01T00:00:00",
}


class TestListMembers:
    def test_list_members(self, client):
        """GET /api/team returns org members."""
        client._mock_supabase.set_table_data("noctus_users", [SAMPLE_MEMBER])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_members_no_auth(self, client):
        """401 when no authorization header."""
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401


class TestInvite:
    def test_invite_no_auth(self, client):
        """401 when no authorization header."""
        resp = client.raw().post("/api/team/invite", json={
            "email": "test@test.com",
            "role": "member",
        })
        assert resp.status_code == 401


class TestRemoveMember:
    def test_remove_no_auth(self, client):
        """401 when no authorization header."""
        resp = client.raw().delete(f"/api/team/{USER_ID}")
        assert resp.status_code == 401

    def test_remove_requires_admin(self, client):
        """403 when non-admin tries to remove a member."""
        resp = client.delete(f"/api/team/{USER_ID}")
        assert resp.status_code in (400, 403)
