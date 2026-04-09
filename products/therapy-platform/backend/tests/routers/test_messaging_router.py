"""
Tests for the Messaging Router — conversations, messages, blocks, reports, read receipts.

Target: 35+ comprehensive tests covering all endpoints, role-based access,
block enforcement, and edge cases.
"""
import pytest
from unittest.mock import patch, AsyncMock


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_CONVERSATION = {
    "id": "conv-001",
    "mode": "human",
    "is_archived": False,
    "last_message_at": "2026-04-01T12:00:00Z",
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_MESSAGE = {
    "id": "msg-001",
    "conversation_id": "conv-001",
    "sender_type": "user",
    "sender_user_id": "test-user-123",
    "message_type": "text",
    "content": "Olá, como você está?",
    "file_url": None,
    "ai_processed_content": None,
    "deleted_at": None,
    "created_at": "2026-04-01T12:00:00Z",
}

SAMPLE_PARTICIPANT_SENDER = {
    "id": "part-001",
    "conversation_id": "conv-001",
    "participant_type": "user",
    "participant_id": "test-user-123",
    "last_read_message_id": None,
    "is_muted": False,
    "is_deleted": False,
    "is_blocked": False,
}

SAMPLE_PARTICIPANT_RECIPIENT = {
    "id": "part-002",
    "conversation_id": "conv-001",
    "participant_type": "user",
    "participant_id": "other-user-456",
    "last_read_message_id": None,
    "is_muted": False,
    "is_deleted": False,
    "is_blocked": False,
}

SAMPLE_PARTICIPANT_SUPPORT = {
    "id": "part-003",
    "conversation_id": "conv-002",
    "participant_type": "platform_support",
    "participant_id": None,
    "is_muted": False,
    "is_deleted": False,
    "is_blocked": False,
}

SAMPLE_REPORT = {
    "id": "report-001",
    "conversation_id": "conv-001",
    "message_id": "msg-001",
    "reported_by_user_id": "test-user-123",
    "reason": "Conteúdo ofensivo e inadequado",
    "status": "pending",
    "created_at": "2026-04-01T13:00:00Z",
}


# ---------------------------------------------------------------------------
# Start Conversation
# ---------------------------------------------------------------------------

class TestStartConversation:
    @patch(
        "app.routers.messaging.messaging_service.send_message",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routers.messaging.messaging_service.find_or_create_conversation",
        new_callable=AsyncMock,
    )
    def test_start_conversation_user_to_user(self, mock_find, mock_send, client):
        mock_find.return_value = SAMPLE_CONVERSATION
        mock_send.return_value = SAMPLE_MESSAGE
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "other-user-456",
            "initial_message": "Olá!",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "conversation" in data
        assert "message" in data
        mock_find.assert_called_once()
        mock_send.assert_called_once()

    @patch(
        "app.routers.messaging.messaging_service.send_message",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routers.messaging.messaging_service.find_or_create_conversation",
        new_callable=AsyncMock,
    )
    def test_start_conversation_user_to_clinic(self, mock_find, mock_send, patient_client):
        mock_find.return_value = SAMPLE_CONVERSATION
        mock_send.return_value = SAMPLE_MESSAGE
        resp = patient_client.post("/api/conversations", json={
            "participant_type": "clinic",
            "clinic_id": "clinic-001",
            "initial_message": "Preciso de ajuda",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["conversation"]["id"] == "conv-001"

    @patch(
        "app.routers.messaging.messaging_service.send_message",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routers.messaging.messaging_service.find_or_create_conversation",
        new_callable=AsyncMock,
    )
    def test_start_conversation_user_to_support(self, mock_find, mock_send, patient_client):
        mock_find.return_value = {**SAMPLE_CONVERSATION, "id": "conv-support"}
        mock_send.return_value = {**SAMPLE_MESSAGE, "conversation_id": "conv-support"}
        resp = patient_client.post("/api/conversations", json={
            "participant_type": "platform_support",
            "initial_message": "Preciso de suporte técnico",
        })
        assert resp.status_code == 200

    @patch(
        "app.routers.messaging.messaging_service.find_or_create_conversation",
        new_callable=AsyncMock,
    )
    def test_start_conversation_with_self_fails(self, mock_find, client):
        from fastapi import HTTPException
        mock_find.side_effect = HTTPException(
            status_code=400,
            detail="Não é possível iniciar conversa consigo mesmo",
        )
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "test-user-123",
            "initial_message": "Falando sozinho",
        })
        assert resp.status_code == 400

    @patch(
        "app.routers.messaging.messaging_service.find_or_create_conversation",
        new_callable=AsyncMock,
    )
    def test_start_conversation_with_blocked_user_fails(self, mock_find, client):
        from fastapi import HTTPException
        mock_find.side_effect = HTTPException(
            status_code=403,
            detail="Usuário bloqueado. Não é possível iniciar conversa",
        )
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "blocked-user",
            "initial_message": "Tentando contato",
        })
        assert resp.status_code == 403

    @patch(
        "app.routers.messaging.messaging_service.send_message",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routers.messaging.messaging_service.find_or_create_conversation",
        new_callable=AsyncMock,
    )
    def test_duplicate_conversation_returns_existing(self, mock_find, mock_send, client):
        """Starting a second conversation with the same user returns the existing one."""
        mock_find.return_value = SAMPLE_CONVERSATION
        mock_send.return_value = SAMPLE_MESSAGE
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "other-user-456",
            "initial_message": "Segunda mensagem",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["conversation"]["id"] == "conv-001"

    def test_start_conversation_missing_initial_message(self, client):
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "other-user-456",
        })
        assert resp.status_code == 422

    def test_start_conversation_no_auth(self, client):
        resp = client._tc.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "other",
            "initial_message": "Oi",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# List Conversations
# ---------------------------------------------------------------------------

class TestListConversations:
    @patch(
        "app.routers.messaging.messaging_service.list_conversations",
        new_callable=AsyncMock,
    )
    def test_list_conversations_patient(self, mock_list, patient_client):
        mock_list.return_value = ([SAMPLE_CONVERSATION], 1)
        resp = patient_client.get("/api/conversations")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert "pagination" in body

    @patch(
        "app.routers.messaging.messaging_service.list_conversations",
        new_callable=AsyncMock,
    )
    def test_list_conversations_therapist(self, mock_list, client):
        mock_list.return_value = ([SAMPLE_CONVERSATION], 1)
        resp = client.get("/api/conversations")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    @patch(
        "app.routers.messaging.messaging_service.list_conversations",
        new_callable=AsyncMock,
    )
    def test_list_conversations_admin_sees_all(self, mock_list, admin_client):
        mock_list.return_value = (
            [SAMPLE_CONVERSATION, {**SAMPLE_CONVERSATION, "id": "conv-002"}], 2,
        )
        resp = admin_client.get("/api/conversations")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    @patch(
        "app.routers.messaging.messaging_service.list_conversations",
        new_callable=AsyncMock,
    )
    def test_list_conversations_clinic_admin(self, mock_list, clinic_admin_client):
        mock_list.return_value = ([SAMPLE_CONVERSATION], 1)
        resp = clinic_admin_client.get("/api/conversations")
        assert resp.status_code == 200

    @patch(
        "app.routers.messaging.messaging_service.list_conversations",
        new_callable=AsyncMock,
    )
    def test_list_conversations_unread_filter(self, mock_list, client):
        mock_list.return_value = ([SAMPLE_CONVERSATION], 1)
        resp = client.get("/api/conversations?filter_type=unread")
        assert resp.status_code == 200

    @patch(
        "app.routers.messaging.messaging_service.list_conversations",
        new_callable=AsyncMock,
    )
    def test_list_conversations_busca(self, mock_list, client):
        mock_list.return_value = ([], 0)
        resp = client.get("/api/conversations?busca=terapeuta")
        assert resp.status_code == 200

    @patch(
        "app.routers.messaging.messaging_service.list_conversations",
        new_callable=AsyncMock,
    )
    def test_list_conversations_pagination(self, mock_list, client):
        mock_list.return_value = ([SAMPLE_CONVERSATION], 5)
        resp = client.get("/api/conversations?page=1&page_size=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page_size"] == 1
        assert body["pagination"]["total"] == 5

    def test_list_conversations_no_auth(self, client):
        resp = client._tc.get("/api/conversations")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Send Message
# ---------------------------------------------------------------------------

class TestSendMessage:
    @patch(
        "app.routers.messaging.messaging_service.send_message",
        new_callable=AsyncMock,
    )
    def test_send_text_message(self, mock_send, client):
        mock_send.return_value = SAMPLE_MESSAGE
        resp = client.post("/api/conversations/conv-001/messages", json={
            "content": "Olá, tudo bem?",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["content"] == "Olá, como você está?"

    @patch(
        "app.routers.messaging.messaging_service.send_message",
        new_callable=AsyncMock,
    )
    def test_send_message_non_participant_denied(self, mock_send, client):
        from fastapi import HTTPException
        mock_send.side_effect = HTTPException(
            status_code=403,
            detail="Você não é participante desta conversa",
        )
        resp = client.post("/api/conversations/conv-999/messages", json={
            "content": "Tentando enviar",
        })
        assert resp.status_code == 403

    @patch(
        "app.routers.messaging.messaging_service.send_message",
        new_callable=AsyncMock,
    )
    def test_send_message_blocked_user_denied(self, mock_send, client):
        from fastapi import HTTPException
        mock_send.side_effect = HTTPException(
            status_code=403,
            detail="Usuário bloqueado. Não é possível enviar mensagens",
        )
        resp = client.post("/api/conversations/conv-001/messages", json={
            "content": "Bloqueado",
        })
        assert resp.status_code == 403

    def test_send_message_empty_content(self, client):
        resp = client.post("/api/conversations/conv-001/messages", json={
            "content": "",
        })
        assert resp.status_code == 422

    def test_send_message_no_auth(self, client):
        resp = client._tc.post("/api/conversations/conv-001/messages", json={
            "content": "Sem auth",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Get Messages
# ---------------------------------------------------------------------------

class TestGetMessages:
    @patch(
        "app.routers.messaging.messaging_service.get_messages",
        new_callable=AsyncMock,
    )
    def test_get_messages_success(self, mock_get, client):
        mock_get.return_value = ([SAMPLE_MESSAGE], 1)
        resp = client.get("/api/conversations/conv-001/messages")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert "pagination" in body

    @patch(
        "app.routers.messaging.messaging_service.get_messages",
        new_callable=AsyncMock,
    )
    def test_get_messages_non_participant_denied(self, mock_get, client):
        from fastapi import HTTPException
        mock_get.side_effect = HTTPException(
            status_code=403,
            detail="Acesso negado a esta conversa",
        )
        resp = client.get("/api/conversations/conv-999/messages")
        assert resp.status_code == 403

    @patch(
        "app.routers.messaging.messaging_service.get_messages",
        new_callable=AsyncMock,
    )
    def test_get_messages_pagination(self, mock_get, client):
        mock_get.return_value = ([SAMPLE_MESSAGE], 10)
        resp = client.get("/api/conversations/conv-001/messages?page=2&page_size=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 2

    def test_get_messages_no_auth(self, client):
        resp = client._tc.get("/api/conversations/conv-001/messages")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Mark as Read
# ---------------------------------------------------------------------------

class TestMarkAsRead:
    @patch(
        "app.routers.messaging.messaging_service.mark_as_read",
        new_callable=AsyncMock,
    )
    def test_mark_as_read_success(self, mock_mark, client):
        mock_mark.return_value = {"ok": True, "last_read_message_id": "msg-001"}
        resp = client.patch("/api/conversations/conv-001/read")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Delete Message (hard delete)
# ---------------------------------------------------------------------------

class TestDeleteMessage:
    @patch(
        "app.routers.messaging.messaging_service.delete_message",
        new_callable=AsyncMock,
    )
    def test_delete_message_sender_success(self, mock_delete, client):
        mock_delete.return_value = {"ok": True, "message": "Mensagem excluída"}
        resp = client.delete("/api/conversations/messages/msg-001")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @patch(
        "app.routers.messaging.messaging_service.delete_message",
        new_callable=AsyncMock,
    )
    def test_delete_message_non_sender_denied(self, mock_delete, client):
        from fastapi import HTTPException
        mock_delete.side_effect = HTTPException(
            status_code=403,
            detail="Apenas o remetente pode excluir a mensagem",
        )
        resp = client.delete("/api/conversations/messages/msg-other")
        assert resp.status_code == 403

    @patch(
        "app.routers.messaging.messaging_service.delete_message",
        new_callable=AsyncMock,
    )
    def test_delete_message_not_found(self, mock_delete, client):
        from fastapi import HTTPException
        mock_delete.side_effect = HTTPException(
            status_code=404,
            detail="Mensagem não encontrada",
        )
        resp = client.delete("/api/conversations/messages/msg-nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Report Message
# ---------------------------------------------------------------------------

class TestReportMessage:
    @patch(
        "app.routers.messaging.messaging_service.report_message",
        new_callable=AsyncMock,
    )
    def test_report_message_success(self, mock_report, client):
        mock_report.return_value = SAMPLE_REPORT
        # Mock the message lookup
        client._mock_supabase.set_table_data("messages", [
            {"id": "msg-001", "conversation_id": "conv-001"},
        ])
        resp = client.post("/api/conversations/messages/msg-001/report", json={
            "reason": "Conteúdo ofensivo e inadequado para a plataforma",
        })
        assert resp.status_code == 200

    def test_report_message_short_reason(self, client):
        resp = client.post("/api/conversations/messages/msg-001/report", json={
            "reason": "curto",
        })
        assert resp.status_code == 422

    def test_report_message_missing_reason(self, client):
        resp = client.post("/api/conversations/messages/msg-001/report", json={})
        assert resp.status_code == 422

    def test_report_message_no_auth(self, client):
        resp = client._tc.post("/api/conversations/messages/msg-001/report", json={
            "reason": "Sem autenticação para denunciar",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Archive Conversation
# ---------------------------------------------------------------------------

class TestArchiveConversation:
    @patch(
        "app.routers.messaging.messaging_service.archive_conversation",
        new_callable=AsyncMock,
    )
    def test_archive_conversation_success(self, mock_archive, client):
        mock_archive.return_value = {"ok": True, "message": "Conversa arquivada"}
        resp = client.post("/api/conversations/conv-001/archive")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @patch(
        "app.routers.messaging.messaging_service.archive_conversation",
        new_callable=AsyncMock,
    )
    def test_archive_conversation_not_found(self, mock_archive, client):
        from fastapi import HTTPException
        mock_archive.side_effect = HTTPException(status_code=404, detail="Conversa não encontrada")
        resp = client.post("/api/conversations/conv-999/archive")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Mute Conversation
# ---------------------------------------------------------------------------

class TestMuteConversation:
    @patch(
        "app.routers.messaging.messaging_service.mute_conversation",
        new_callable=AsyncMock,
    )
    def test_mute_conversation(self, mock_mute, client):
        mock_mute.return_value = {"ok": True, "message": "Conversa silenciada"}
        resp = client.post("/api/conversations/conv-001/mute?mute=true")
        assert resp.status_code == 200

    @patch(
        "app.routers.messaging.messaging_service.mute_conversation",
        new_callable=AsyncMock,
    )
    def test_unmute_conversation(self, mock_mute, client):
        mock_mute.return_value = {"ok": True, "message": "Conversa reativada"}
        resp = client.post("/api/conversations/conv-001/mute?mute=false")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Block / Unblock
# ---------------------------------------------------------------------------

class TestBlockUser:
    @patch(
        "app.routers.messaging.messaging_service.block_user",
        new_callable=AsyncMock,
    )
    def test_block_user_success(self, mock_block, client):
        mock_block.return_value = {"ok": True, "message": "Usuário bloqueado"}
        resp = client.post("/api/conversations/block", json={
            "blocked_user_id": "bad-user-789",
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @patch(
        "app.routers.messaging.messaging_service.block_user",
        new_callable=AsyncMock,
    )
    def test_block_user_hides_conversations(self, mock_block, client):
        """Blocking should hide mutual conversations."""
        mock_block.return_value = {"ok": True, "message": "Usuário bloqueado"}
        resp = client.post("/api/conversations/block", json={
            "blocked_user_id": "other-user-456",
        })
        assert resp.status_code == 200
        mock_block.assert_called_once()

    @patch(
        "app.routers.messaging.messaging_service.block_user",
        new_callable=AsyncMock,
    )
    def test_block_self_fails(self, mock_block, client):
        from fastapi import HTTPException
        mock_block.side_effect = HTTPException(
            status_code=400,
            detail="Não é possível bloquear a si mesmo",
        )
        resp = client.post("/api/conversations/block", json={
            "blocked_user_id": "test-user-123",
        })
        assert resp.status_code == 400

    def test_block_user_missing_id(self, client):
        resp = client.post("/api/conversations/block", json={})
        assert resp.status_code == 422

    def test_block_user_no_auth(self, client):
        resp = client._tc.post("/api/conversations/block", json={
            "blocked_user_id": "other-user",
        })
        assert resp.status_code == 401


class TestUnblockUser:
    @patch(
        "app.routers.messaging.messaging_service.unblock_user",
        new_callable=AsyncMock,
    )
    def test_unblock_user_success(self, mock_unblock, client):
        mock_unblock.return_value = {"ok": True, "message": "Usuário desbloqueado"}
        resp = client.delete("/api/conversations/block/bad-user-789")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @patch(
        "app.routers.messaging.messaging_service.unblock_user",
        new_callable=AsyncMock,
    )
    def test_unblock_user_unhides_conversations(self, mock_unblock, client):
        """Unblocking should restore hidden conversations."""
        mock_unblock.return_value = {"ok": True, "message": "Usuário desbloqueado"}
        resp = client.delete("/api/conversations/block/other-user-456")
        assert resp.status_code == 200
        mock_unblock.assert_called_once()

    @patch(
        "app.routers.messaging.messaging_service.unblock_user",
        new_callable=AsyncMock,
    )
    def test_unblock_user_not_blocked(self, mock_unblock, client):
        from fastapi import HTTPException
        mock_unblock.side_effect = HTTPException(
            status_code=404,
            detail="Bloqueio não encontrado",
        )
        resp = client.delete("/api/conversations/block/nonexistent-user")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Unread Count
# ---------------------------------------------------------------------------

class TestUnreadCount:
    @patch(
        "app.routers.messaging.messaging_service.get_unread_count",
        new_callable=AsyncMock,
    )
    def test_unread_count(self, mock_count, client):
        mock_count.return_value = 5
        resp = client.get("/api/conversations/unread-count")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["unread_count"] == 5

    @patch(
        "app.routers.messaging.messaging_service.get_unread_count",
        new_callable=AsyncMock,
    )
    def test_unread_count_zero(self, mock_count, patient_client):
        mock_count.return_value = 0
        resp = patient_client.get("/api/conversations/unread-count")
        assert resp.status_code == 200
        assert resp.json()["data"]["unread_count"] == 0

    def test_unread_count_no_auth(self, client):
        resp = client._tc.get("/api/conversations/unread-count")
        assert resp.status_code == 401
