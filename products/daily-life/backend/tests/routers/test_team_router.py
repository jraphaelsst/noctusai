"""
Tests for the team management router — provided by seed framework.

These tests validate the framework's standard team router as consumed
by the Daily Life product. Detailed team behavior is tested in the
seed framework package itself.
"""

MOCK_MEMBERS = [
    {
        "id": "user-abc",
        "nome": "Alice",
        "email": "alice@test.com",
        "org_role": "owner",
        "avatar_url": None,
        "created_at": "2026-01-01T00:00:00Z",
    },
]


class TestListMembers:
    """GET /api/team"""

    def test_list_members(self, client):
        client.mock_supabase.set_table_data("noctus_users", MOCK_MEMBERS)
        resp = client.get("/api/team")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_list_members_no_auth(self, client):
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401


class TestInviteMember:
    """POST /api/team/invite"""

    def test_invite_no_auth(self, client):
        resp = client.raw().post("/api/team/invite", json={
            "email": "new@example.com",
            "role": "member",
        })
        assert resp.status_code == 401


class TestAcceptInvite:
    """GET /api/team/accept/validate and POST /api/team/accept"""

    def test_validate_no_token(self, client):
        resp = client.raw().get("/api/team/accept/validate")
        assert resp.status_code == 422  # missing required query param


class TestRemoveMember:
    """DELETE /api/team/{user_id}"""

    def test_remove_no_auth(self, client):
        resp = client.raw().delete("/api/team/some-user-id")
        assert resp.status_code == 401
