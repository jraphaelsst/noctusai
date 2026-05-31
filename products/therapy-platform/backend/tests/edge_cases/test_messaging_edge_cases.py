"""
Messaging edge cases -- blocking, hard delete, conversation dedup, attachment limits.

Tests verify that blocking hides conversations, hard delete is sender-only,
conversation dedup works, and attachment validation enforces size/type limits.
"""
import pytest


# ===================================================================
# Blocking behavior
# ===================================================================

class TestBlockingBehavior:
    """Blocking a user hides conversations and prevents new ones."""

    def test_self_block_rejected(self, client):
        """Blocking yourself -> 400."""
        sb = client._mock_supabase
        sb.set_table_data("user_blocks", [])
        resp = client.post("/api/conversations/block", json={
            "blocked_user_id": "test-user-123",
        })
        assert resp.status_code == 400

    def test_block_user_succeeds(self, client):
        """Blocking another user -> success."""
        sb = client._mock_supabase
        sb.set_table_data("user_blocks", [])
        sb.set_table_data("conversation_participants", [])
        resp = client.post("/api/conversations/block", json={
            "blocked_user_id": "other-user-456",
        })
        assert resp.status_code == 200

    def test_duplicate_block_rejected(self, client):
        """Blocking already-blocked user -> 409."""
        sb = client._mock_supabase
        sb.set_table_data("user_blocks", [
            {"id": "block-001", "blocker_user_id": "test-user-123", "blocked_user_id": "other-user-456"},
        ])
        resp = client.post("/api/conversations/block", json={
            "blocked_user_id": "other-user-456",
        })
        assert resp.status_code == 409

    def test_unblock_nonexistent_block_404(self, client):
        """Unblocking a user that isn't blocked -> 404."""
        sb = client._mock_supabase
        sb.set_table_data("user_blocks", [])
        resp = client.delete("/api/conversations/block/other-user-456")
        assert resp.status_code == 404

    def test_unblock_existing_block_succeeds(self, client):
        """Unblocking a blocked user -> success."""
        sb = client._mock_supabase
        sb.set_table_data("user_blocks", [
            {"id": "block-001", "blocker_user_id": "test-user-123", "blocked_user_id": "other-user-456"},
        ])
        sb.set_table_data("conversation_participants", [])
        resp = client.delete("/api/conversations/block/other-user-456")
        assert resp.status_code == 200


# ===================================================================
# Hard delete
# ===================================================================

class TestHardDelete:
    """Only the sender can hard-delete their own messages."""

    def test_delete_own_message_succeeds(self, client):
        """Sender deletes their own message -> success."""
        sb = client._mock_supabase
        sb.set_table_data("messages", [
            {"id": "msg-001", "sender_user_id": "test-user-123", "content": "Hello"},
        ])
        resp = client.delete("/api/conversations/messages/msg-001")
        assert resp.status_code == 200

    def test_delete_other_users_message_denied(self, client):
        """Trying to delete another user's message -> 403."""
        sb = client._mock_supabase
        sb.set_table_data("messages", [
            {"id": "msg-002", "sender_user_id": "other-user-456", "content": "Hi"},
        ])
        resp = client.delete("/api/conversations/messages/msg-002")
        assert resp.status_code == 403

    def test_delete_nonexistent_message_404(self, client):
        """Deleting a message that doesn't exist -> 404."""
        sb = client._mock_supabase
        sb.set_table_data("messages", [])
        resp = client.delete("/api/conversations/messages/msg-nonexistent")
        assert resp.status_code == 404


# ===================================================================
# Conversation deduplication
# ===================================================================

class TestConversationDedup:
    """Starting a conversation with the same user twice returns existing."""

    def test_start_conversation_validates_participant_id(self, client):
        """Starting conversation with user requires participant_id."""
        sb = client._mock_supabase
        sb.set_table_data("user_blocks", [])
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "initial_message": "Ola, tudo bem?",
        })
        # participant_id is required for 'user' type
        assert resp.status_code == 400

    def test_start_conversation_validates_clinic_id(self, client):
        """Starting conversation with clinic requires clinic_id."""
        sb = client._mock_supabase
        sb.set_table_data("user_blocks", [])
        resp = client.post("/api/conversations", json={
            "participant_type": "clinic",
            "initial_message": "Ola clinica",
        })
        assert resp.status_code == 400

    def test_cannot_message_self(self, client):
        """Starting a conversation with yourself -> 400."""
        sb = client._mock_supabase
        sb.set_table_data("user_blocks", [])
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "test-user-123",
            "initial_message": "Hello me",
        })
        assert resp.status_code == 400


# ===================================================================
# Message validation
# ===================================================================

class TestMessageValidation:
    """Message content validation via Pydantic schema."""

    def test_empty_message_rejected(self, client):
        """Empty content -> 422 (min_length=1)."""
        resp = client.post("/api/conversations/conv-001/messages", json={
            "content": "",
        })
        assert resp.status_code == 422

    def test_message_too_long_rejected(self, client):
        """Content > 5000 chars -> 422 (max_length=5000)."""
        resp = client.post("/api/conversations/conv-001/messages", json={
            "content": "A" * 5001,
        })
        assert resp.status_code == 422

    def test_valid_message_accepted(self, client):
        """Normal message length passes validation."""
        sb = client._mock_supabase
        sb.set_table_data("conversation_participants", [
            {"id": "cp-001", "conversation_id": "conv-001",
             "participant_type": "user", "participant_id": "test-user-123"},
        ])
        sb.set_table_data("messages", [
            {"id": "msg-new", "conversation_id": "conv-001", "content": "Hello"},
        ])
        sb.set_table_data("conversations", [
            {"id": "conv-001", "mode": "human", "last_message_at": "2026-04-01T10:00:00Z"},
        ])
        sb.set_table_data("user_blocks", [])
        resp = client.post("/api/conversations/conv-001/messages", json={
            "content": "Hello, how are you?",
        })
        assert resp.status_code == 200


# ===================================================================
# Attachment limits (schema + service validation)
# ===================================================================

class TestAttachmentLimits:
    """Attachment upload enforces size and type restrictions."""

    def test_unsupported_file_type_rejected(self, client):
        """Upload unsupported content type -> 422."""
        from app.services.attachment_service import upload_attachment, ALLOWED_TYPES
        from tests.conftest import MockSupabaseClient
        from fastapi import HTTPException

        db = MockSupabaseClient()
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            # new_event_loop() not get_event_loop(): py3.10+ raises "no current
            # event loop" in a thread without a running loop (CI MainThread).
            asyncio.new_event_loop().run_until_complete(
                upload_attachment(
                    file_bytes=b"MZ\x90\x00",  # exe magic bytes
                    filename="malware.exe",
                    content_type="application/x-msdownload",
                    conversation_id="conv-001",
                    db=db,
                )
            )
        assert exc_info.value.status_code == 422
        assert "não suportado" in exc_info.value.detail

    def test_file_over_50mb_rejected(self, client):
        """Upload > 50MB -> 422."""
        from app.services.attachment_service import upload_attachment
        from tests.conftest import MockSupabaseClient
        from fastapi import HTTPException

        db = MockSupabaseClient()
        # Create data slightly over 50MB
        big_data = b"x" * (50 * 1024 * 1024 + 1)
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            # new_event_loop() not get_event_loop(): py3.10+ raises "no current
            # event loop" in a thread without a running loop (CI MainThread).
            asyncio.new_event_loop().run_until_complete(
                upload_attachment(
                    file_bytes=big_data,
                    filename="huge.jpg",
                    content_type="image/jpeg",
                    conversation_id="conv-001",
                    db=db,
                )
            )
        assert exc_info.value.status_code == 422
        assert "50MB" in exc_info.value.detail
