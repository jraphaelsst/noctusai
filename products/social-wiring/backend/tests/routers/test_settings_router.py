"""Tests for settings_router — keys/status + recipients CRUD shape.

YouTube OAuth endpoints depend on a real google-auth Flow; tests for
those are deferred to Phase-1.5b once we add a stubbable OAuth seam.
"""


class TestKeysStatus:
    """The keys/status endpoint never echoes secrets — only configured /
    missing flags."""

    def test_returns_keys_status_shape(self, client, override_settings):
        # Force every secret-bearing field to a known state so the test
        # is independent of whatever .env the dev machine carries.
        override_settings(
            youtube_client_id="",
            youtube_client_secret="configured-value",
            encryption_key="",
            smtp_user="user@example.com",
            smtp_password="",
            waha_base_url="",
            waha_api_key="",
        )

        resp = client.get("/api/settings/keys/status")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["youtube_client_id"]["health"] == "missing"
        assert data["youtube_client_secret"]["health"] == "configured"
        assert data["encryption_key"]["health"] == "missing"
        assert data["smtp_user"]["health"] == "configured"
        assert data["smtp_password"]["health"] == "missing"

        # No secret value leaks.
        body_text = resp.text
        assert "configured-value" not in body_text
        assert "user@example.com" not in body_text


class TestKeysStatusAuth:
    def test_unauthenticated_rejected(self, client):
        resp = client.raw().get("/api/settings/keys/status")
        # Either 401 (no credentials) or 403 (no token) — both surface
        # as "not authenticated"; the seed dependency picks the shape.
        assert resp.status_code in (401, 403)


class TestRecipientsValidation:
    """Boundary validation lives in the schema, but verifying it through
    the router catches accidentally bypassing the schema in code."""

    def test_recipient_without_channel_rejected(self, client):
        resp = client.post(
            "/api/settings/recipients",
            json={"name": "No-channel recipient"},
        )
        assert resp.status_code == 422
        assert "at least one of" in resp.text.lower()

    def test_invalid_whatsapp_number_rejected(self, client):
        resp = client.post(
            "/api/settings/recipients",
            json={
                "name": "Bad number",
                "whatsapp_number": "not-e164",
            },
        )
        assert resp.status_code == 422
