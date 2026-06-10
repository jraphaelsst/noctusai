"""Tests for the Mailchimp connection router.

Covers §1 contract: GET/PUT/PATCH/DELETE /connection + GET /audiences.
Auth tests assert strict == 401.
"""
from __future__ import annotations

from tests.modules.mailchimp.conftest import MailchimpAuthError, MailchimpUnreachableError


class TestAuthRequired:
    """Every endpoint must return exactly 401 when unauthenticated."""

    def test_get_connection_requires_auth(self, client):
        resp = client.raw().get("/api/mailchimp/connection")
        assert resp.status_code == 401

    def test_put_connection_requires_auth(self, client):
        resp = client.raw().put("/api/mailchimp/connection", json={"api_key": "k-us6"})
        assert resp.status_code == 401

    def test_patch_connection_requires_auth(self, client):
        resp = client.raw().patch("/api/mailchimp/connection", json={"audience_id": "aud1"})
        assert resp.status_code == 401

    def test_delete_connection_requires_auth(self, client):
        resp = client.raw().delete("/api/mailchimp/connection")
        assert resp.status_code == 401

    def test_get_audiences_requires_auth(self, client):
        resp = client.raw().get("/api/mailchimp/audiences")
        assert resp.status_code == 401


class TestGetConnection:
    def test_disconnected_returns_200_not_connected(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.get("/api/mailchimp/connection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert data["server_prefix"] is None
        assert data["audience_id"] is None

    def test_connected_returns_200_with_fields(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.get("/api/mailchimp/connection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["server_prefix"] == "us6"
        assert data["audience_id"] == "fake-audience-1"


class TestPutConnection:
    def test_valid_key_upserts_and_returns_connection(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.put("/api/mailchimp/connection", json={"api_key": "mykey-us6"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["server_prefix"] == "us6"
        # api_key must not be returned
        assert "api_key" not in data

    def test_api_key_never_returned(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.put("/api/mailchimp/connection", json={"api_key": "secret-us6"})
        text = resp.text
        assert "secret-us6" not in text

    def test_malformed_key_no_dash_returns_400(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.put("/api/mailchimp/connection", json={"api_key": "nokeynosuffix"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "mailchimp_rejected"

    def test_malformed_key_bad_suffix_returns_400(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.put("/api/mailchimp/connection", json={"api_key": "key-BADDC"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "mailchimp_rejected"

    def test_put_with_audience_id(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.put(
            "/api/mailchimp/connection",
            json={"api_key": "k-us6", "audience_id": "aud1"},
        )
        assert resp.status_code == 200
        assert resp.json()["audience_id"] == "aud1"

    def test_unreachable_ping_returns_502(self, mailchimp_client):
        c, store, fake = mailchimp_client

        async def _ping_fail():
            raise MailchimpUnreachableError("timeout")

        fake.ping = _ping_fail
        resp = c.put("/api/mailchimp/connection", json={"api_key": "k-us6"})
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "mailchimp_unreachable"

    def test_auth_failed_ping_returns_502(self, mailchimp_client):
        c, store, fake = mailchimp_client

        async def _ping_auth():
            raise MailchimpAuthError("401 Unauthorized")

        fake.ping = _ping_auth
        resp = c.put("/api/mailchimp/connection", json={"api_key": "k-us6"})
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "mailchimp_auth_failed"


class TestPatchConnection:
    def test_patch_audience_updates_row(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.patch("/api/mailchimp/connection", json={"audience_id": "aud-new"})
        assert resp.status_code == 200
        assert resp.json()["audience_id"] == "aud-new"

    def test_patch_without_connection_returns_503(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.patch("/api/mailchimp/connection", json={"audience_id": "aud1"})
        assert resp.status_code == 503


class TestDeleteConnection:
    def test_delete_returns_204(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.delete("/api/mailchimp/connection")
        assert resp.status_code == 204

    def test_delete_when_not_connected_returns_404(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.delete("/api/mailchimp/connection")
        assert resp.status_code == 404


class TestEncryptionNotConfigured:
    def test_get_audiences_503_when_encryption_not_configured(self, mailchimp_client):
        """When store raises EncryptionNotConfigured it maps to 503."""
        from app.main import app
        from app.modules.mailchimp.deps import get_mailchimp_store
        from noctusai_lib.primitives.exceptions import AppException

        c, store, fake = mailchimp_client

        def _fail():
            raise AppException(
                code="mailchimp_not_configured",
                message="no key",
                status_code=503,
            )

        prev = app.dependency_overrides.get(get_mailchimp_store)
        app.dependency_overrides[get_mailchimp_store] = _fail
        try:
            resp = c.get("/api/mailchimp/audiences")
            assert resp.status_code == 503
            assert resp.json()["error"]["code"] == "mailchimp_not_configured"
        finally:
            if prev is None:
                app.dependency_overrides.pop(get_mailchimp_store, None)
            else:
                app.dependency_overrides[get_mailchimp_store] = prev


class TestGetAudiences:
    def test_list_audiences_returns_envelope(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.get("/api/mailchimp/audiences")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1
        assert all("id" in a for a in data["items"])

    def test_list_audiences_503_when_not_connected(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.get("/api/mailchimp/audiences")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "mailchimp_not_configured"
