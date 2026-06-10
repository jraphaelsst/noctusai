"""Tests for the Mailchimp contacts router — /api/mailchimp/contacts."""
from __future__ import annotations


class TestAuthRequired:
    def test_list_contacts_requires_auth(self, client):
        resp = client.raw().get("/api/mailchimp/contacts")
        assert resp.status_code == 401

    def test_get_contact_requires_auth(self, client):
        resp = client.raw().get("/api/mailchimp/contacts/foo@example.com")
        assert resp.status_code == 401

    def test_put_contact_requires_auth(self, client):
        resp = client.raw().put(
            "/api/mailchimp/contacts/foo@example.com",
            json={"status": "subscribed"},
        )
        assert resp.status_code == 401

    def test_delete_contact_requires_auth(self, client):
        resp = client.raw().delete("/api/mailchimp/contacts/foo@example.com")
        assert resp.status_code == 401


class TestNotConfigured:
    def test_list_503_when_not_connected(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.get("/api/mailchimp/contacts")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "mailchimp_not_configured"


class TestListContacts:
    def test_empty_audience_returns_envelope(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.get("/api/mailchimp/contacts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_with_status_filter(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        c.put("/api/mailchimp/contacts/a@x.com", json={"status": "subscribed"})
        resp = c.get("/api/mailchimp/contacts?status=subscribed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_pagination_params(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.get("/api/mailchimp/contacts?count=10&offset=0")
        assert resp.status_code == 200


class TestUpsertContact:
    def test_put_creates_member(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.put("/api/mailchimp/contacts/new@example.com", json={"status": "subscribed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert data["status"] == "subscribed"

    def test_put_with_name_and_tags(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.put(
            "/api/mailchimp/contacts/tagged@example.com",
            json={"status": "subscribed", "first_name": "Ana", "tags": ["vip", "new"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["first_name"] == "Ana"

    def test_api_key_not_in_contact_response(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.put("/api/mailchimp/contacts/x@example.com", json={"status": "subscribed"})
        assert "api_key" not in resp.text


class TestGetContact:
    def test_get_existing_member(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        c.put("/api/mailchimp/contacts/get@example.com", json={"status": "subscribed"})
        resp = c.get("/api/mailchimp/contacts/get@example.com")
        assert resp.status_code == 200
        assert resp.json()["email"] == "get@example.com"

    def test_get_missing_returns_404(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.get("/api/mailchimp/contacts/nobody@example.com")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


class TestArchiveContact:
    def test_delete_returns_204(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        c.put("/api/mailchimp/contacts/del@example.com", json={"status": "subscribed"})
        resp = c.delete("/api/mailchimp/contacts/del@example.com")
        assert resp.status_code == 204

    def test_delete_missing_returns_404(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.delete("/api/mailchimp/contacts/nobody@example.com")
        assert resp.status_code == 404
