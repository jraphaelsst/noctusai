"""
Tests for Admin Users Router.

GET    /api/admin/users
GET    /api/admin/users/{user_id}
PATCH  /api/admin/users/{user_id}
DELETE /api/admin/users/{user_id}
"""
import pytest
from datetime import date, timedelta

today = date.today().isoformat()
yesterday = (date.today() - timedelta(days=1)).isoformat()

SAMPLE_USERS = [
    {
        "id": "user-1",
        "email": "alice@example.com",
        "nome": "Alice Silva",
        "org_id": "org-1",
        "role": "user",
        "org_role": "member",
        "created_at": yesterday,
    },
    {
        "id": "user-2",
        "email": "bob@example.com",
        "nome": "Bob Santos",
        "org_id": "org-1",
        "role": "admin",
        "org_role": "owner",
        "created_at": today,
    },
]


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_list_users_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", SAMPLE_USERS)

        resp = admin_client.get("/api/admin/users")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert "pagination" in body
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 20

    def test_list_users_with_search(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", SAMPLE_USERS)

        resp = admin_client.get("/api/admin/users?busca=alice")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_list_users_with_role_filter(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", [SAMPLE_USERS[1]])

        resp = admin_client.get("/api/admin/users?role=admin")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_list_users_pagination(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", SAMPLE_USERS)

        resp = admin_client.get("/api/admin/users?page=2&page_size=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 2
        assert body["pagination"]["page_size"] == 1

    def test_list_users_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/users")
        assert resp.status_code == 403

    def test_list_users_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/admin/users")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/users/{user_id}
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_get_user_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "user-1",
            "email": "alice@example.com",
            "nome": "Alice Silva",
            "org_id": "org-1",
            "role": "user",
            "org_role": "member",
            "created_at": today,
        })
        mock_sb.set_table_data("organizations", {
            "id": "org-1",
            "nome": "Test Corp",
            "slug": "test-corp",
            "plano": "pro",
        })

        resp = admin_client.get("/api/admin/users/user-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "user-1"
        assert data["organization"]["id"] == "org-1"

    def test_get_user_without_org(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "user-no-org",
            "email": "orphan@example.com",
            "nome": "Orphan User",
            "org_id": None,
            "role": "user",
            "org_role": "member",
            "created_at": today,
        })

        resp = admin_client.get("/api/admin/users/user-no-org")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["organization"] is None

    def test_get_user_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = admin_client.get("/api/admin/users/nonexistent")
        assert resp.status_code == 404

    def test_get_user_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/users/user-1")
        assert resp.status_code == 403

    def test_get_user_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/admin/users/user-1")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{user_id}
# ---------------------------------------------------------------------------

class TestUpdateUser:
    def test_update_user_role(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            # First call: pre-check (select id)
            {"id": "user-1"},
            # Second call: update result
            [{"id": "user-1", "role": "admin", "nome": "Alice Silva", "email": "alice@example.com"}],
        ])

        resp = admin_client.patch("/api/admin/users/user-1", json={"role": "admin"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "admin"

    def test_update_user_nome(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1"},
            [{"id": "user-1", "nome": "Alice Updated", "role": "user", "email": "alice@example.com"}],
        ])

        resp = admin_client.patch("/api/admin/users/user-1", json={"nome": "Alice Updated"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "Alice Updated"

    def test_update_user_org_role(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1"},
            [{"id": "user-1", "org_role": "admin", "nome": "Alice Silva", "email": "alice@example.com"}],
        ])

        resp = admin_client.patch("/api/admin/users/user-1", json={"org_role": "admin"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["org_role"] == "admin"

    def test_update_user_empty_body(self, admin_client):
        resp = admin_client.patch("/api/admin/users/user-1", json={})
        assert resp.status_code == 400

    def test_update_user_invalid_role(self, admin_client):
        resp = admin_client.patch("/api/admin/users/user-1", json={"role": "superadmin"})
        assert resp.status_code == 422

    def test_update_user_invalid_org_role(self, admin_client):
        resp = admin_client.patch("/api/admin/users/user-1", json={"org_role": "supreme"})
        assert resp.status_code == 422

    def test_update_user_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = admin_client.patch("/api/admin/users/nonexistent", json={"nome": "X"})
        assert resp.status_code == 404

    def test_update_user_forbidden_for_non_admin(self, client):
        resp = client.patch("/api/admin/users/user-1", json={"role": "admin"})
        assert resp.status_code == 403

    def test_update_user_unauthenticated(self, unauth_client):
        resp = unauth_client.patch("/api/admin/users/user-1", json={"role": "admin"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/admin/users/{user_id}
# ---------------------------------------------------------------------------

class TestDeleteUser:
    def test_delete_user_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"id": "user-1"})

        resp = admin_client.delete("/api/admin/users/user-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "excluído" in body["message"]

    def test_delete_user_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = admin_client.delete("/api/admin/users/nonexistent")
        assert resp.status_code == 404

    def test_delete_user_forbidden_for_non_admin(self, client):
        resp = client.delete("/api/admin/users/user-1")
        assert resp.status_code == 403

    def test_delete_user_unauthenticated(self, unauth_client):
        resp = unauth_client.delete("/api/admin/users/user-1")
        assert resp.status_code == 401
