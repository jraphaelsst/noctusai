"""Tests for the Mailchimp connection router.

Covers §1 contract: GET/PUT/PATCH/DELETE /connection + GET /audiences.
Auth tests assert strict == 401.
"""
from __future__ import annotations

from uuid import uuid4

from app.dependencies import coerce_org_uuid
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


class TestPerClienteConnection:
    """Migration 019 — Mailchimp connections scoped per (org, client_id)."""

    def test_put_with_client_id_scopes_connection(self, mailchimp_client_with_clients):
        """(a) PUT + GET with a client_id round-trips the scoped connection."""
        c, store, fake, org_client_id, foreign_client_id = mailchimp_client_with_clients
        resp = c.put(
            "/api/mailchimp/connection",
            json={
                "api_key": "cli-us6",
                "audience_id": "aud-cli",
                "client_id": str(org_client_id),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["connected"] is True
        assert data["client_id"] == str(org_client_id)
        assert data["audience_id"] == "aud-cli"

        resp = c.get(f"/api/mailchimp/connection?client_id={org_client_id}")
        assert resp.status_code == 200
        d = resp.json()
        assert d["connected"] is True
        assert d["client_id"] == str(org_client_id)
        assert d["audience_id"] == "aud-cli"

    def test_get_without_client_id_returns_org_default(
        self, mailchimp_client_with_clients
    ):
        """(b) The org-default (client_id NULL) is independent from a cliente row."""
        c, store, fake, org_client_id, foreign_client_id = mailchimp_client_with_clients
        # Seed ONLY a per-cliente connection.
        c.put(
            "/api/mailchimp/connection",
            json={
                "api_key": "cli-us6",
                "audience_id": "aud-cli",
                "client_id": str(org_client_id),
            },
        )
        # Org-default probe → not connected, client_id echoed as null.
        resp = c.get("/api/mailchimp/connection")
        assert resp.status_code == 200
        d = resp.json()
        assert d["connected"] is False
        assert d["client_id"] is None

        # Seed the org-default connection.
        c.put("/api/mailchimp/connection", json={"api_key": "org-us6", "audience_id": "aud-org"})
        d = c.get("/api/mailchimp/connection").json()
        assert d["connected"] is True
        assert d["client_id"] is None
        assert d["audience_id"] == "aud-org"

        # The per-cliente connection stays independently scoped.
        d_cli = c.get(f"/api/mailchimp/connection?client_id={org_client_id}").json()
        assert d_cli["audience_id"] == "aud-cli"
        assert d_cli["client_id"] == str(org_client_id)

    def test_put_with_foreign_org_client_id_rejected_404(
        self, mailchimp_client_with_clients
    ):
        """(c) A client_id owned by a DIFFERENT org is rejected."""
        c, store, fake, org_client_id, foreign_client_id = mailchimp_client_with_clients
        resp = c.put(
            "/api/mailchimp/connection",
            json={"api_key": "x-us6", "client_id": str(foreign_client_id)},
        )
        assert resp.status_code == 404, resp.text

    def test_put_with_unknown_client_id_rejected_404(
        self, mailchimp_client_with_clients
    ):
        """(c') A wholly unknown client_id is rejected."""
        c, store, fake, org_client_id, foreign_client_id = mailchimp_client_with_clients
        resp = c.put(
            "/api/mailchimp/connection",
            json={"api_key": "x-us6", "client_id": str(uuid4())},
        )
        assert resp.status_code == 404

    def test_put_idempotent_per_scope(self, mailchimp_client_with_clients):
        """(d) Repeated PUTs to the same (org, client_id) replace, never duplicate."""
        c, store, fake, org_client_id, foreign_client_id = mailchimp_client_with_clients
        c.put(
            "/api/mailchimp/connection",
            json={"api_key": "cli-us6", "client_id": str(org_client_id)},
        )
        c.put(
            "/api/mailchimp/connection",
            json={"api_key": "cli2-eu1", "client_id": str(org_client_id)},
        )
        # Exactly one row for that scope (white-box: query the store's client).
        org_id = coerce_org_uuid("test-org-123")
        rows = store._table().select("*").eq("org_id", str(org_id)).execute().data or []
        scoped = [
            r for r in rows
            if store._norm_client_id(r.get("client_id")) == str(org_client_id)
        ]
        assert len(scoped) == 1
        # The replacement won (server_prefix updated).
        d = c.get(f"/api/mailchimp/connection?client_id={org_client_id}").json()
        assert d["server_prefix"] == "eu1"

    def test_org_default_and_cliente_coexist(self, mailchimp_client_with_clients):
        """(e-router) Org-default + per-cliente rows coexist without collision."""
        c, store, fake, org_client_id, foreign_client_id = mailchimp_client_with_clients
        c.put("/api/mailchimp/connection", json={"api_key": "org-us6", "audience_id": "aud-org"})
        c.put(
            "/api/mailchimp/connection",
            json={"api_key": "cli-us6", "audience_id": "aud-cli", "client_id": str(org_client_id)},
        )
        assert c.get("/api/mailchimp/connection").json()["audience_id"] == "aud-org"
        assert (
            c.get(f"/api/mailchimp/connection?client_id={org_client_id}").json()["audience_id"]
            == "aud-cli"
        )


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
