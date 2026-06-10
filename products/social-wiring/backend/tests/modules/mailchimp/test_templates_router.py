"""Tests for the Mailchimp templates router — /api/mailchimp/templates."""
from __future__ import annotations


class TestAuthRequired:
    def test_list_requires_auth(self, client):
        assert client.raw().get("/api/mailchimp/templates").status_code == 401

    def test_create_requires_auth(self, client):
        resp = client.raw().post(
            "/api/mailchimp/templates",
            json={"name": "T", "html": "<html/>"},
        )
        assert resp.status_code == 401

    def test_get_requires_auth(self, client):
        assert client.raw().get("/api/mailchimp/templates/1").status_code == 401

    def test_patch_requires_auth(self, client):
        resp = client.raw().patch("/api/mailchimp/templates/1", json={"name": "x"})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.raw().delete("/api/mailchimp/templates/1").status_code == 401


class TestNotConfigured:
    def test_503_when_not_connected(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.get("/api/mailchimp/templates")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "mailchimp_not_configured"


class TestTemplateCrud:
    def test_create_template(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.post(
            "/api/mailchimp/templates",
            json={"name": "Newsletter", "html": "<html><body>Hi</body></html>"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Newsletter"
        assert "id" in data

    def test_list_templates_envelope(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        c.post("/api/mailchimp/templates", json={"name": "T1", "html": "<p/>"})
        resp = c.get("/api/mailchimp/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data and "total" in data
        assert data["total"] >= 1

    def test_get_template(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        tid = c.post("/api/mailchimp/templates", json={"name": "GT", "html": "<p/>"}).json()["id"]
        resp = c.get(f"/api/mailchimp/templates/{tid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GT"

    def test_get_missing_template_returns_404(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.get("/api/mailchimp/templates/99999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_patch_template_name(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        tid = c.post("/api/mailchimp/templates", json={"name": "Old", "html": "<p/>"}).json()["id"]
        resp = c.patch(f"/api/mailchimp/templates/{tid}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_delete_template(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        tid = c.post("/api/mailchimp/templates", json={"name": "Del", "html": "<p/>"}).json()["id"]
        resp = c.delete(f"/api/mailchimp/templates/{tid}")
        assert resp.status_code == 204

    def test_delete_missing_returns_404(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.delete("/api/mailchimp/templates/99999")
        assert resp.status_code == 404


class TestEditUrl:
    def test_edit_url_computed_server_side(self, connected_mailchimp_client):
        """edit_url must be https://{dc}.admin.mailchimp.com/templates/edit?id={id}."""
        c, store, fake = connected_mailchimp_client
        resp = c.post("/api/mailchimp/templates", json={"name": "EU", "html": "<p/>"})
        assert resp.status_code == 201
        data = resp.json()
        tid = data["id"]
        expected_prefix = "https://us6.admin.mailchimp.com/templates/edit?id="
        assert data["edit_url"] is not None
        assert data["edit_url"].startswith(expected_prefix), (
            f"edit_url {data['edit_url']!r} should start with {expected_prefix!r}"
        )
        assert str(tid) in data["edit_url"]
