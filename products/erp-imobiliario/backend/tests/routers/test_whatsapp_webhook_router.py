"""
Tests for the WhatsApp Webhook router — WAHA event processing.
Covers HMAC verification, incoming messages, ack status updates,
session management, and edge cases.
"""
import hashlib
import hmac
import json
import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Webhook endpoint (unauthenticated — called by WAHA server)
# ---------------------------------------------------------------------------

class TestWAHAWebhook:

    def _post_webhook(self, client, event_data, headers=None):
        """Helper to POST to the webhook endpoint."""
        return client._tc.post(
            "/api/whatsapp/webhook",
            json=event_data,
            headers=headers or {},
        )

    def test_incoming_message_stored(self, client):
        """Incoming message event creates a whatsapp_messages record."""
        # Config lookup returns a matching org
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])
        # Client lookup by phone
        client._mock_supabase.set_table_data("clientes", [
            {"id": "cliente-1"},
        ])
        client._mock_supabase.set_table_data("whatsapp_messages", [])

        resp = self._post_webhook(client, {
            "event": "message",
            "session": "default",
            "payload": {
                "body": "Ola, tenho interesse",
                "from": "5511999999999@c.us",
                "id": "waha-msg-001",
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["stored"] is True

    def test_incoming_message_no_client_match(self, client):
        """Message from unknown phone still stores with cliente_id=None."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])
        client._mock_supabase.set_table_data("clientes", [])
        client._mock_supabase.set_table_data("whatsapp_messages", [])

        resp = self._post_webhook(client, {
            "event": "message",
            "session": "default",
            "payload": {
                "body": "Hello",
                "from": "5511000000000@c.us",
                "id": "waha-msg-002",
            },
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_incoming_message_empty_body_ignored(self, client):
        """Empty message body is ignored."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])

        resp = self._post_webhook(client, {
            "event": "message",
            "session": "default",
            "payload": {
                "body": "",
                "from": "5511999999999@c.us",
                "id": "waha-msg-003",
            },
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        assert resp.json()["reason"] == "empty_message"

    def test_incoming_message_no_from_ignored(self, client):
        """Missing 'from' field is ignored."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])

        resp = self._post_webhook(client, {
            "event": "message",
            "session": "default",
            "payload": {
                "body": "Hello",
                "from": "",
                "id": "waha-msg-004",
            },
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_ack_updates_status_to_read(self, client):
        """ACK level 3 maps to 'read' status."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])
        client._mock_supabase.set_table_data("whatsapp_messages", [])

        resp = self._post_webhook(client, {
            "event": "message.ack",
            "session": "default",
            "payload": {
                "ack": 3,
                "id": {"id": "waha-msg-001"},
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["updated_status"] == "read"

    def test_ack_updates_status_to_delivered(self, client):
        """ACK level 2 maps to 'delivered'."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])
        client._mock_supabase.set_table_data("whatsapp_messages", [])

        resp = self._post_webhook(client, {
            "event": "message.ack",
            "session": "default",
            "payload": {
                "ack": 2,
                "id": {"id": "waha-msg-002"},
            },
        })
        assert resp.status_code == 200
        assert resp.json()["updated_status"] == "delivered"

    def test_ack_updates_status_to_sent(self, client):
        """ACK level 1 maps to 'sent'."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])
        client._mock_supabase.set_table_data("whatsapp_messages", [])

        resp = self._post_webhook(client, {
            "event": "message.ack",
            "session": "default",
            "payload": {
                "ack": 1,
                "id": {"id": "waha-msg-003"},
            },
        })
        assert resp.status_code == 200
        assert resp.json()["updated_status"] == "sent"

    def test_ack_unknown_level_ignored(self, client):
        """Unknown ACK level (e.g. 0 or 5) is ignored."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])

        resp = self._post_webhook(client, {
            "event": "message.ack",
            "session": "default",
            "payload": {
                "ack": 0,
                "id": {"id": "waha-msg-004"},
            },
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        assert "unknown_ack" in resp.json()["reason"]

    def test_ack_no_msg_id_ignored(self, client):
        """ACK without message ID is ignored."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])

        resp = self._post_webhook(client, {
            "event": "message.ack",
            "session": "default",
            "payload": {
                "ack": 3,
                "id": {"id": ""},
            },
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_session_status_event(self, client):
        """session.status events are acknowledged."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])

        resp = self._post_webhook(client, {
            "event": "session.status",
            "session": "default",
            "payload": {"status": "CONNECTED"},
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_unhandled_event_type(self, client):
        """Unknown event types are ignored gracefully."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])

        resp = self._post_webhook(client, {
            "event": "group.join",
            "session": "default",
            "payload": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert "unhandled_event" in data["reason"]

    def test_unknown_session_ignored(self, client):
        """Event for unconfigured WAHA session is ignored."""
        client._mock_supabase.set_table_data("whatsapp_config", [])

        resp = self._post_webhook(client, {
            "event": "message",
            "session": "nonexistent-session",
            "payload": {"body": "test", "from": "5511999999999@c.us"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "session_not_configured"


# ---------------------------------------------------------------------------
# HMAC signature verification
# ---------------------------------------------------------------------------

class TestWebhookHMACVerification:

    def test_valid_signature_accepted(self, client):
        """Request with valid HMAC signature is processed."""
        secret = "my-webhook-secret"
        payload = {
            "event": "session.status",
            "session": "default",
            "payload": {"status": "CONNECTED"},
        }
        body_bytes = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()

        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": secret, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])

        resp = client._tc.post(
            "/api/whatsapp/webhook",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "x-hub-signature": sig,
            },
        )
        assert resp.status_code == 200

    def test_invalid_signature_rejected(self, client):
        """Request with wrong HMAC signature returns 401."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": "real-secret", "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])

        resp = client._tc.post(
            "/api/whatsapp/webhook",
            content=json.dumps({
                "event": "message",
                "session": "default",
                "payload": {"body": "test", "from": "5511999@c.us"},
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "x-hub-signature": "sha256=wrong-signature",
            },
        )
        assert resp.status_code == 401

    def test_missing_signature_when_secret_configured_rejected(self, client):
        """Missing x-hub-signature header when secret is configured returns 401."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": "secret-value", "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])

        resp = self._post_webhook_raw(client, {
            "event": "message",
            "session": "default",
            "payload": {"body": "test", "from": "5511999@c.us"},
        })
        assert resp.status_code == 401

    def test_no_verification_when_no_secret(self, client):
        """No verification is done when webhook_secret is not configured."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"org_id": "org-1", "webhook_secret": None, "waha_session_name": "default", "provider": "waha", "is_active": True},
        ])
        client._mock_supabase.set_table_data("clientes", [])
        client._mock_supabase.set_table_data("whatsapp_messages", [])

        resp = client._tc.post(
            "/api/whatsapp/webhook",
            json={
                "event": "message",
                "session": "default",
                "payload": {"body": "Hi", "from": "5511999@c.us", "id": "x"},
            },
        )
        assert resp.status_code == 200

    def _post_webhook_raw(self, client, event_data):
        return client._tc.post(
            "/api/whatsapp/webhook",
            json=event_data,
        )


# ---------------------------------------------------------------------------
# Authenticated session endpoints
# ---------------------------------------------------------------------------

class TestWAHASessions:

    def test_listar_sessions(self, client):
        """GET /api/whatsapp/sessions returns WAHA configs."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"id": "cfg-1", "provider": "waha", "waha_session_name": "default", "is_active": True},
        ])

        resp = client.get("/api/whatsapp/sessions")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["provider"] == "waha"

    def test_listar_sessions_empty(self, client):
        """GET /api/whatsapp/sessions returns empty list when no configs."""
        client._mock_supabase.set_table_data("whatsapp_config", [])

        resp = client.get("/api/whatsapp/sessions")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_iniciar_session_no_config(self, client):
        """POST /api/whatsapp/sessions/start fails when no WAHA config exists."""
        # .single() on empty data returns None-like → triggers 400
        client._mock_supabase.set_table_data("whatsapp_config", [])

        resp = client.post("/api/whatsapp/sessions/start", json={
            "session_name": "default",
        })
        assert resp.status_code == 400

    def test_iniciar_session_no_waha_url(self, client):
        """POST /api/whatsapp/sessions/start fails when waha_api_url is empty."""
        client._mock_supabase.set_table_data("whatsapp_config", [
            {"id": "cfg-1", "provider": "waha", "waha_api_url": None, "waha_api_key": None, "waha_session_name": "default", "is_active": True},
        ])

        resp = client.post("/api/whatsapp/sessions/start", json={
            "session_name": "default",
        })
        assert resp.status_code == 400
