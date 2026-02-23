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
    def test_delete_profile_secure(self, client):
        client._mock_supabase.set_table_data("profiles", {"nome": "ToDelete"})
        client._mock_supabase.auth.admin = MagicMock()
        client._mock_supabase.auth.admin.delete_user = MagicMock(return_value=None)
        resp = client.delete("/api/profiles/p1")
        assert resp.status_code == 200
