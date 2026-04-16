"""
Integration tests for Personal Finance — team endpoints provided by seed framework.

Detailed team behavior is tested in the seed framework package itself.
Product-level e2e tests validate that the framework endpoints are accessible.
"""


class TestTeamFrameworkEndpoints:
    def test_team_list_accessible(self, client):
        client.mock_supabase.set_table_data("noctus_users", [
            {"id": "u1", "nome": "Alice", "email": "a@test.com", "org_role": "owner"},
        ])
        resp = client.get("/api/team")
        assert resp.status_code == 200

    def test_team_invite_requires_auth(self, client):
        resp = client.raw().post("/api/team/invite", json={"email": "t@t.com"})
        assert resp.status_code == 401

    def test_notifications_accessible(self, client):
        client.mock_supabase.set_table_data("notifications", [])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200

    def test_health_accessible(self, client):
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["product"] == "Financas Pessoais"
