"""Tests for the Support router — /api/support (admin inbox)."""
import pytest
from unittest.mock import patch, MagicMock

SAMPLE_SUPPORT_CONVO = {
    "id": "convo-support-001",
    "mode": "human",
    "last_message_at": "2026-04-01T10:00:00Z",
    "created_at": "2026-04-01T09:00:00Z",
}

SAMPLE_MESSAGE = {
    "id": "msg-001",
    "conversation_id": "convo-support-001",
    "sender_type": "user",
    "sender_user_id": "patient-001",
    "message_type": "text",
    "content": "Preciso de ajuda com meu agendamento",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestListSupportConversations:
    def test_admin_sees_support_inbox(self, admin_client):
        admin_client._mock_supabase.set_table_data("conversations", [SAMPLE_SUPPORT_CONVO])
        admin_client._mock_supabase.set_table_data("conversation_participants", [
            {"conversation_id": "convo-support-001", "participant_type": "platform_support"},
        ])
        resp = admin_client.get("/api/support/conversations")
        assert resp.status_code == 200

    def test_therapist_forbidden(self, client):
        resp = client.get("/api/support/conversations")
        assert resp.status_code == 403

    def test_patient_forbidden(self, patient_client):
        resp = patient_client.get("/api/support/conversations")
        assert resp.status_code == 403

    def test_no_auth(self, admin_client):
        resp = admin_client._tc.get("/api/support/conversations")
        assert resp.status_code == 401


class TestGetSupportMessages:
    def test_admin_reads_messages(self, admin_client):
        admin_client._mock_supabase.set_table_data("messages", [SAMPLE_MESSAGE])
        admin_client._mock_supabase.set_table_data("conversation_participants", [
            {"conversation_id": "convo-support-001", "participant_type": "platform_support"},
        ])
        resp = admin_client.get("/api/support/conversations/convo-support-001/messages")
        assert resp.status_code == 200

    def test_therapist_forbidden(self, client):
        resp = client.get("/api/support/conversations/convo-support-001/messages")
        assert resp.status_code == 403


class TestAdminReply:
    def test_admin_replies(self, admin_client):
        admin_client._mock_supabase.set_table_data("conversation_participants", [
            {"conversation_id": "convo-support-001", "participant_type": "platform_support"},
        ])
        admin_client._mock_supabase.set_table_data("messages", [SAMPLE_MESSAGE])
        admin_client._mock_supabase.set_table_data("conversations", [SAMPLE_SUPPORT_CONVO])
        resp = admin_client.post(
            "/api/support/conversations/convo-support-001/messages",
            json={"content": "Claro, posso ajudar!"},
        )
        assert resp.status_code == 200

    def test_patient_cannot_reply_via_support_endpoint(self, patient_client):
        resp = patient_client.post(
            "/api/support/conversations/convo-support-001/messages",
            json={"content": "teste"},
        )
        assert resp.status_code == 403

    def test_no_auth(self, admin_client):
        resp = admin_client._tc.post(
            "/api/support/conversations/convo-support-001/messages",
            json={"content": "teste"},
        )
        assert resp.status_code == 401
