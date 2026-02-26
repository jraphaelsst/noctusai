"""
Tests for Roles Router.

GET    /api/roles
POST   /api/roles           (requires team:manage permission)
PATCH  /api/roles/{id}      (requires team:manage permission)
DELETE /api/roles/{id}      (requires team:manage permission)
"""
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# GET /api/roles
# ---------------------------------------------------------------------------

class TestListRoles:
    def test_list_roles_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", [
            {"id": "r1", "name": "Owner", "slug": "owner", "is_system": True},
            {"id": "r2", "name": "Admin", "slug": "admin", "is_system": True},
        ])

        resp = client.get("/api/roles")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_roles_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.get("/api/roles")
        assert resp.status_code == 404

    def test_list_roles_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/roles")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/roles (requires team:manage)
# ---------------------------------------------------------------------------

class TestCreateRole:
    def test_create_role_with_permission(self, admin_client):
        """admin_client has check_permission returning True."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        # roles is queried multiple times:
        #   1. existing slug check → empty
        #   2. slug_check_system → empty
        #   3. slug_check_org → empty
        #   4. insert → returns the new role
        mock_sb.set_table_responses("roles", [
            [],  # existing
            [],  # slug_check_system
            [],  # slug_check_org
            [{"id": "new-role", "name": "Custom Role", "slug": "custom-role"}],
        ])

        resp = admin_client.post("/api/roles", json={
            "name": "Custom Role",
            "slug": "custom-role",
            "permissions": ["team:read", "billing:read"],
        })
        assert resp.status_code == 200

    def test_create_role_without_permission(self, client):
        """client has check_permission returning False."""
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "member",
            "role": "user",
        })

        resp = client.post("/api/roles", json={
            "name": "Custom",
            "slug": "custom",
            "permissions": ["team:read"],
        })
        assert resp.status_code == 403

    def test_create_role_unknown_permission(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", [])

        resp = admin_client.post("/api/roles", json={
            "name": "Bad Role",
            "slug": "bad-role",
            "permissions": ["nonexistent:permission"],
        })
        assert resp.status_code == 400

    def test_create_role_wildcard_permission_rejected(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", [])

        resp = admin_client.post("/api/roles", json={
            "name": "Wildcard Role",
            "slug": "wildcard",
            "permissions": ["*"],
        })
        assert resp.status_code == 400

    def test_create_role_missing_fields(self, admin_client):
        resp = admin_client.post("/api/roles", json={
            "name": "Missing Slug",
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/roles/{id} (requires team:manage)
# ---------------------------------------------------------------------------

class TestUpdateRole:
    def test_update_custom_role(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", [
            {"id": "r1", "is_system": False, "org_id": "org-1", "name": "Updated"},
        ])

        resp = admin_client.patch("/api/roles/r1", json={
            "name": "Updated Role",
        })
        assert resp.status_code == 200

    def test_update_system_role_rejected(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", {
            "id": "r-sys",
            "is_system": True,
            "org_id": None,
        })

        resp = admin_client.patch("/api/roles/r-sys", json={
            "name": "Hacked Owner",
        })
        assert resp.status_code == 403

    def test_update_role_empty_body(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", {
            "id": "r1",
            "is_system": False,
            "org_id": "org-1",
        })

        resp = admin_client.patch("/api/roles/r1", json={})
        assert resp.status_code == 400

    def test_update_role_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", None)

        resp = admin_client.patch("/api/roles/nonexistent", json={
            "name": "Updated",
        })
        assert resp.status_code == 404

    def test_update_role_without_permission(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "member",
            "role": "user",
        })

        resp = client.patch("/api/roles/r1", json={"name": "Try"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/roles/{id} (requires team:manage)
# ---------------------------------------------------------------------------

class TestDeleteRole:
    def test_delete_custom_role_no_users(self, admin_client):
        mock_sb = admin_client.mock_supabase
        # noctus_users is queried twice:
        #   1. _get_user_profile (.single) → admin profile
        #   2. users_with_role check → empty (no users have this role)
        mock_sb.set_table_responses("noctus_users", [
            {"id": "admin-user-456", "org_id": "org-1", "org_role": "admin", "role": "admin"},
            [],  # no users with the custom role
        ])
        mock_sb.set_table_data("roles", {
            "id": "r1",
            "slug": "custom",
            "is_system": False,
            "org_id": "org-1",
        })

        resp = admin_client.delete("/api/roles/r1")
        assert resp.status_code == 200

    def test_delete_system_role_rejected(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", {
            "id": "r-sys",
            "slug": "owner",
            "is_system": True,
            "org_id": None,
        })

        resp = admin_client.delete("/api/roles/r-sys")
        assert resp.status_code == 403

    def test_delete_role_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "admin-user-456",
            "org_id": "org-1",
            "org_role": "admin",
            "role": "admin",
        })
        mock_sb.set_table_data("roles", None)

        resp = admin_client.delete("/api/roles/nonexistent")
        assert resp.status_code == 404

    def test_delete_role_without_permission(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "org_role": "member",
            "role": "user",
        })

        resp = client.delete("/api/roles/r1")
        assert resp.status_code == 403
