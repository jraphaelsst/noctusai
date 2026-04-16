"""Tests for team router — provided by seed framework."""


class TestTeamEndpoints:
    def test_list_members(self, client):
        client.mock_supabase.set_table_data("noctus_users", [
            {"id": "u1", "nome": "Alice", "email": "a@test.com", "org_role": "owner"},
        ])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_list_no_auth(self, client):
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401

    def test_invite_no_auth(self, client):
        resp = client.raw().post("/api/team/invite", json={"email": "t@t.com"})
        assert resp.status_code == 401
