"""Tests for contacts router."""
from noctusai_lib.testing import MockSupabaseResponse


MOCK_CONTACT = {
    "id": "c1",
    "org_id": "test-org-123",
    "email": "lead@test.com",
    "nome": "Lead Test",
    "empresa": "Test Inc",
    "tags": ["vip"],
    "status": "active",
    "source": "manual",
    "created_at": "2026-01-01T00:00:00Z",
}


class TestListContacts:
    def test_list(self, client):
        client.mock_supabase.set_table_data("contacts", [MOCK_CONTACT])
        resp = client.get("/api/contacts")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_no_auth(self, client):
        resp = client.raw().get("/api/contacts")
        assert resp.status_code == 401


class TestCreateContact:
    def test_create(self, client):
        client.mock_supabase.set_table_data("contacts", [MOCK_CONTACT])
        resp = client.post("/api/contacts", json={
            "email": "lead@test.com",
            "nome": "Lead Test",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "lead@test.com"


class TestGetContact:
    def test_get(self, client):
        client.mock_supabase.set_table_data("contacts", [MOCK_CONTACT])
        resp = client.get("/api/contacts/c1")
        assert resp.status_code == 200

    def test_not_found(self, client):
        client.mock_supabase.set_table_data("contacts", [])
        resp = client.get("/api/contacts/nonexistent")
        assert resp.status_code == 404


class TestUpdateContact:
    def test_update(self, client):
        updated = {**MOCK_CONTACT, "nome": "Updated Name"}
        client.mock_supabase.set_table_data("contacts", [updated])
        resp = client.patch("/api/contacts/c1", json={"nome": "Updated Name"})
        assert resp.status_code == 200


class TestDeleteContact:
    def test_delete(self, client):
        client.mock_supabase.set_table_data("contacts", [MOCK_CONTACT])
        resp = client.delete("/api/contacts/c1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestImportContacts:
    def test_import(self, client):
        client.mock_supabase.set_table_data("contacts", [MOCK_CONTACT])
        resp = client.post("/api/contacts/import", json={
            "contacts": [
                {"email": "lead@test.com", "nome": "Lead"},
            ]
        })
        assert resp.status_code == 200
