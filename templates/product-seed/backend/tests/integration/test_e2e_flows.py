"""
E2E tests for the {{PRODUCT_NAME}} — validates the seed framework's standard
routers work as complete user journeys.

These tests prove the framework itself works. If these fail, every product
that inherits from the framework is affected.
"""
from noctusai_lib.testing import MockSupabaseResponse


# ==========================================================================
# 1. Framework standard endpoints exist and respond correctly
# ==========================================================================

class TestFrameworkEndpoints:
    """All framework-provided endpoints must exist and respond."""

    def test_health_returns_product_info(self, client):
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["product"] == "{{PRODUCT_NAME}}"
        assert "version" in data

    def test_team_list_requires_auth(self, client):
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401

    def test_team_invite_requires_auth(self, client):
        resp = client.raw().post("/api/team/invite", json={"email": "t@t.com"})
        assert resp.status_code == 401

    def test_team_validate_requires_token(self, client):
        resp = client.raw().get("/api/team/accept/validate")
        assert resp.status_code == 422  # missing query param

    def test_team_invitations_requires_auth(self, client):
        resp = client.raw().get("/api/team/invitations")
        assert resp.status_code == 401

    def test_team_delete_requires_auth(self, client):
        resp = client.raw().delete("/api/team/some-id")
        assert resp.status_code == 401

    def test_notificacoes_list_requires_auth(self, client):
        resp = client.raw().get("/api/notificacoes")
        assert resp.status_code == 401

    def test_notificacoes_contagem_requires_auth(self, client):
        resp = client.raw().get("/api/notificacoes/contagem")
        assert resp.status_code == 401

    def test_notificacoes_mark_read_requires_auth(self, client):
        resp = client.raw().patch("/api/notificacoes/some-id/ler")
        assert resp.status_code == 401

    def test_notificacoes_mark_all_requires_auth(self, client):
        resp = client.raw().post("/api/notificacoes/ler-todas")
        assert resp.status_code == 401


# ==========================================================================
# 2. Authenticated team flow
# ==========================================================================

class TestTeamFlow:
    """Team management through the framework's standard router."""

    def test_list_members_returns_data(self, client):
        """Authenticated user can list org members."""
        client._mock_supabase.set_table_data("noctus_users", [
            {"id": "u1", "nome": "Alice", "email": "alice@test.com",
             "org_role": "owner", "avatar_url": None, "created_at": "2026-01-01T00:00:00Z"},
            {"id": "u2", "nome": "Bob", "email": "bob@test.com",
             "org_role": "member", "avatar_url": None, "created_at": "2026-01-02T00:00:00Z"},
        ])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2

    def test_cannot_remove_self(self, client):
        """Framework prevents self-removal."""
        resp = client.delete("/api/team/test-user-123")
        # Returns 400 (self-removal) or 403 (not admin) — both are correct rejections
        assert resp.status_code in (400, 403)


# ==========================================================================
# 3. Notification flow
# ==========================================================================

class TestNotificationFlow:
    """Notification proxying through the framework's standard router."""

    def test_list_notifications(self, client):
        """Authenticated user can list notifications."""
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1", "user_id": "test-user-123", "type": "system",
             "title": "Welcome", "message": "Hello", "read": False,
             "metadata": {}, "created_at": "2026-01-01T00:00:00Z"},
        ])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1

    def test_count_unread(self, client):
        """Count unread notifications."""
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1"}, {"id": "n2"},
        ])
        resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        assert resp.json()["nao_lidas"] == 2

    def test_mark_one_as_read(self, client):
        """Mark a single notification as read."""
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1", "read": True},
        ])
        resp = client.patch("/api/notificacoes/n1/ler")
        assert resp.status_code == 200

    def test_mark_all_as_read(self, client):
        """Mark all notifications as read."""
        client._mock_supabase.set_table_data("notifications", [])
        resp = client.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 200


# ==========================================================================
# 4. Full auth boundary — every protected endpoint rejects without token
# ==========================================================================

class TestAuthBoundary:
    """Every protected endpoint must return 401 without auth."""

    def test_team_list_401(self, client):
        assert client.raw().get("/api/team").status_code == 401

    def test_team_invite_401(self, client):
        assert client.raw().post("/api/team/invite", json={"email": "t@t.com"}).status_code == 401

    def test_team_invitations_401(self, client):
        assert client.raw().get("/api/team/invitations").status_code == 401

    def test_team_cancel_401(self, client):
        assert client.raw().delete("/api/team/invitations/x").status_code == 401

    def test_team_remove_401(self, client):
        assert client.raw().delete("/api/team/x").status_code == 401

    def test_notificacoes_list_401(self, client):
        assert client.raw().get("/api/notificacoes").status_code == 401

    def test_notificacoes_contagem_401(self, client):
        assert client.raw().get("/api/notificacoes/contagem").status_code == 401

    def test_notificacoes_mark_401(self, client):
        assert client.raw().patch("/api/notificacoes/x/ler").status_code == 401

    def test_notificacoes_mark_all_401(self, client):
        assert client.raw().post("/api/notificacoes/ler-todas").status_code == 401
