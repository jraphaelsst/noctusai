"""
Tests for Profiles router — /api/profiles
"""
import pytest
from unittest.mock import MagicMock


class TestListProfiles:
    def test_list_profiles(self, client):
        client._mock_supabase.set_table_data("profiles", [
            {"id": "p1", "nome": "Admin", "email": "admin@test.com"},
        ])
        resp = client.get("/api/profiles")
        assert resp.status_code == 200


class TestCreateProfile:
    def test_create_profile_success(self, client):
        client._mock_supabase.auth.admin = type("Admin", (), {
            "create_user": lambda self, data: type("Res", (), {"user": type("U", (), {"id": "new-user"})()})()
        })()
        resp = client.post("/api/profiles", json={
            "nome": "novo corretor",
            "email": "novo@test.com",
            "telefone": "11999999999",
            "password": "senha123456",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "Novo Corretor"  # capitalized

    def test_create_profile_missing_password(self, client):
        resp = client.post("/api/profiles", json={
            "nome": "Test", "email": "test@test.com",
        })
        assert resp.status_code == 422

    def test_create_profile_missing_email(self, client):
        resp = client.post("/api/profiles", json={
            "nome": "Test", "password": "123456",
        })
        assert resp.status_code == 422


class TestUpdateProfile:
    def test_update_profile(self, client):
        client._mock_supabase.set_table_data("profiles", {"id": "p1", "nome": "Updated"})
        resp = client.patch("/api/profiles/p1", json={"nome": "Updated Name"})
        assert resp.status_code == 200

    def test_update_empty(self, client):
        resp = client.patch("/api/profiles/p1", json={})
        assert resp.status_code == 400


class TestDeleteProfile:
    """The cross-org guard at routers/profiles.py:115 fails CLOSED.

    Pre-migration-024 (2026-05-03) the column `profiles.org_id` did not
    exist in live DB; `target_profile.data.get("org_id")` always returned
    None and the guard `if target_org and caller_org != target_org` was
    silently bypassed (cross-tenant DELETE was possible). These regression
    tests exercise the four boundary conditions:

    - same-org delete → 200
    - cross-org delete → 403 "Acesso negado"
    - target with NULL org_id (legacy / un-backfilled row) → 403 "...sem
      organização escopada..."
    - self-delete → 400 (existing behavior)
    """

    def _setup(self, client, target_org_id):
        """Seed a profile + arm the auth admin for delete success."""
        client._mock_supabase.set_table_data("profiles", [
            {"id": "p1", "nome": "ToDelete", "org_id": target_org_id},
        ])
        client._mock_supabase.auth.admin = MagicMock()
        client._mock_supabase.auth.admin.delete_user = MagicMock(return_value=None)

    def test_delete_same_org_succeeds(self, client):
        # Default fixture user is `org_id="test-org-123"`.
        self._setup(client, target_org_id="test-org-123")
        resp = client.delete("/api/profiles/p1")
        assert resp.status_code == 200, resp.text

    def test_delete_cross_org_blocked(self, client):
        """Admin of org A cannot delete a profile owned by org B."""
        self._setup(client, target_org_id="other-org-456")
        resp = client.delete("/api/profiles/p1")
        assert resp.status_code == 403
        body = resp.json()
        assert "Acesso negado" in str(body)

    def test_delete_null_org_blocked(self, client):
        """Pre-migration-024 silent-bypass regression guard. Profile with
        NULL org_id (legacy row that didn't backfill) raises 403, never
        falls through to the deletion."""
        self._setup(client, target_org_id=None)
        resp = client.delete("/api/profiles/p1")
        assert resp.status_code == 403
        body = resp.json()
        assert "organização escopada" in str(body) or "organizacao escopada" in str(body)

    def test_delete_self_blocked(self, client):
        """Self-deletion is rejected before the cross-org check runs."""
        # Default fixture user id: see MockUser default. We only need to
        # call DELETE /<same-id>; the early `if profile_id == user.id`
        # check fires regardless of org_id state.
        from noctusai_lib.testing import MockUser
        user = MockUser()  # default test-user
        client._mock_supabase.auth.get_user = MagicMock(
            return_value=type("R", (), {"user": user})()
        )
        resp = client.delete(f"/api/profiles/{user.id}")
        assert resp.status_code == 400
        body = resp.json()
        assert "si mesmo" in str(body)
