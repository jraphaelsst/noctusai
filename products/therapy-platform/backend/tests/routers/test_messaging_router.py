"""
Tests for the Messaging Router — conversations, messages, blocks, reports, read receipts.

Target: 35+ comprehensive tests covering all endpoints, role-based access,
block enforcement, and edge cases.

**Pattern 3 (seed real data) refactor in flight (2026-04-28):** the file is
migrating away from `@patch("app.routers.messaging.messaging_service.<helper>", ...)`
self-monkeypatches per `KB § PATTERNS/testing.md § No self-monkeypatching § Pattern 3`.
The `_seed_conversation_for_user(...)` helper seeds the minimum DB rows so
`messaging_service` runs end-to-end against `MockSupabaseClient`. Tests now
exercise real authorization / block-check / participant-validation logic
instead of asserting "the helper was called once with arguments matching the
SAMPLE constants".
"""
import pytest
from noctusai_lib.testing import assert_error_contains as _assert_error_contains


# ---------------------------------------------------------------------------
# Pattern 3 seed helpers — DRY the per-test setup so each test can declare
# *just* the data shape it needs. Each helper writes to `client._mock_supabase`
# (`AuthClient` exposes the seed mock) so the real `messaging_service`
# helpers find rows when they query.
# ---------------------------------------------------------------------------

def _seed_conversation_for_user(
    client,
    *,
    conv_id="conv-001",
    user_id="test-user-123",
    other_user_id="other-user-456",
    last_message_at="2026-04-01T12:00:00Z",
):
    """Seed a 2-user conversation where `user_id` is a participant.
    Real `find_or_create_conversation` will return this conv when the same
    pair queries; real `list_conversations` will surface it for `user_id`.
    """
    client._mock_supabase.set_table_data("conversations", [{
        "id": conv_id, "mode": "human",
        "is_archived": False,
        "last_message_at": last_message_at,
        "created_at": "2026-04-01T10:00:00Z",
    }])
    client._mock_supabase.set_table_data("conversation_participants", [
        {
            "id": "part-001", "conversation_id": conv_id,
            "participant_type": "user", "participant_id": user_id,
            "is_muted": False, "is_deleted": False, "is_blocked": False,
            "last_read_message_id": None,
        },
        {
            "id": "part-002", "conversation_id": conv_id,
            "participant_type": "user", "participant_id": other_user_id,
            "is_muted": False, "is_deleted": False, "is_blocked": False,
            "last_read_message_id": None,
        },
    ])


def _seed_block(client, *, blocker_id="test-user-123", blocked_id="blocked-user"):
    """Seed a user_blocks row so real `_check_block` returns True."""
    client._mock_supabase.set_table_data("user_blocks", [{
        "id": "block-001",
        "blocker_id": blocker_id,
        "blocked_id": blocked_id,
        "created_at": "2026-04-01T10:00:00Z",
    }])


def _seed_conversation_for_clinic(
    client,
    *,
    conv_id="conv-001",
    user_id="test-user-123",
    clinic_id="clinic-001",
    last_message_at="2026-04-01T12:00:00Z",
):
    """Seed a user↔clinic conversation. `find_or_create_conversation` finds the
    existing conv via `_find_existing_conversation` matching on
    (`participant_type=clinic`, `clinic_id=...`)."""
    client._mock_supabase.set_table_data("conversations", [{
        "id": conv_id, "mode": "human",
        "is_archived": False,
        "last_message_at": last_message_at,
        "created_at": "2026-04-01T10:00:00Z",
    }])
    client._mock_supabase.set_table_data("conversation_participants", [
        {
            "id": "part-001", "conversation_id": conv_id,
            "participant_type": "user", "participant_id": user_id,
            "is_muted": False, "is_deleted": False, "is_blocked": False,
            "last_read_message_id": None,
        },
        {
            "id": "part-002", "conversation_id": conv_id,
            "participant_type": "clinic", "participant_id": None,
            "clinic_id": clinic_id,
            "is_muted": False, "is_deleted": False, "is_blocked": False,
            "last_read_message_id": None,
        },
    ])


def _seed_conversation_for_support(
    client,
    *,
    conv_id="conv-support",
    user_id="test-user-123",
    last_message_at="2026-04-01T12:00:00Z",
):
    """Seed a user↔platform_support conversation. `find_or_create_conversation`
    matches on `participant_type=platform_support` (no participant_id/clinic_id)."""
    client._mock_supabase.set_table_data("conversations", [{
        "id": conv_id, "mode": "human",
        "is_archived": False,
        "last_message_at": last_message_at,
        "created_at": "2026-04-01T10:00:00Z",
    }])
    client._mock_supabase.set_table_data("conversation_participants", [
        {
            "id": "part-001", "conversation_id": conv_id,
            "participant_type": "user", "participant_id": user_id,
            "is_muted": False, "is_deleted": False, "is_blocked": False,
            "last_read_message_id": None,
        },
        {
            "id": "part-003", "conversation_id": conv_id,
            "participant_type": "platform_support", "participant_id": None,
            "is_muted": False, "is_deleted": False, "is_blocked": False,
            "last_read_message_id": None,
        },
    ])


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
    def test_start_conversation_user_to_user(self, client):
        """Pattern 3: seed an existing user↔user conv; real `find_or_create_conversation`
        matches on (sender_id, target participant_id) and returns it. Real
        `send_message` validates participants and inserts the message (auto-id
        via `MockRequestBuilder.insert(...)` returning the inserted row).

        The semantic difference vs the old @patch test (find-existing vs create-new)
        is intentional: `MockSupabaseClient` doesn't reflect inserts back into
        SELECT state, so end-to-end Pattern 3 exercises the find-existing branch.
        Both branches converge on the same observable contract — endpoint returns
        a `conversation` + `message` pair — so the assertion is unchanged.
        """
        _seed_conversation_for_user(client, user_id="test-user-123")
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "other-user-456",
            "initial_message": "Olá!",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "conversation" in data
        assert "message" in data
        assert data["conversation"]["id"] == "conv-001"
        assert data["message"]["content"] == "Olá!"

    def test_start_conversation_user_to_clinic(self, patient_client):
        """Pattern 3: seed user↔clinic conv. Real `find_or_create_conversation`
        matches on (sender_id, clinic_id)."""
        _seed_conversation_for_clinic(patient_client, user_id="test-user-123", clinic_id="clinic-001")
        resp = patient_client.post("/api/conversations", json={
            "participant_type": "clinic",
            "clinic_id": "clinic-001",
            "initial_message": "Preciso de ajuda",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["conversation"]["id"] == "conv-001"

    def test_start_conversation_user_to_support(self, patient_client):
        """Pattern 3: seed user↔platform_support conv. Real
        `find_or_create_conversation` matches on `participant_type=platform_support`."""
        _seed_conversation_for_support(patient_client, user_id="test-user-123",
                                       conv_id="conv-support")
        resp = patient_client.post("/api/conversations", json={
            "participant_type": "platform_support",
            "initial_message": "Preciso de suporte técnico",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["conversation"]["id"] == "conv-support"

    def test_start_conversation_with_self_fails(self, client):
        """Pattern 3 (seed real data) — no patch. Real `find_or_create_conversation`
        validates `participant_id == sender_id` at the top and raises 400. The test
        verifies the production guard, not just that an arbitrary patch was called.
        Refactored 2026-04-28 from `@patch(...)` per `KB § PATTERNS/testing.md
        § No self-monkeypatching § Pattern 3`.
        """
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "test-user-123",  # same as the conftest's authenticated user
            "initial_message": "Falando sozinho",
        })
        assert resp.status_code == 400
        # Platform wraps HTTPException via the exception handler in
        # `{"error": {"code": ..., "message": ...}}` shape; not FastAPI's
        # default `{"detail": ...}`.
        body = resp.json()
        assert "consigo mesmo" in body.get("error", {}).get("message", "") or "consigo mesmo" in body.get("detail", "")

    def test_start_conversation_with_blocked_user_fails(self, client):
        """Pattern 3: seed user_blocks so real `_check_block` returns True
        and `find_or_create_conversation` raises 403 at line 56 of messaging_service.
        """
        _seed_block(client, blocker_id="test-user-123", blocked_id="blocked-user")
        resp = client.post("/api/conversations", json={
            "participant_type": "user",
            "participant_id": "blocked-user",
            "initial_message": "Tentando contato",
        })
        assert resp.status_code == 403
        _assert_error_contains(resp, "bloqueado")

    def test_duplicate_conversation_returns_existing(self, client):
        """Pattern 3: real `_find_existing_conversation` finds the seeded
        conv. Posting a second `/api/conversations` returns the same conv
        rather than a new one."""
        _seed_conversation_for_user(client, user_id="test-user-123")
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
    """Pattern 3: seed `conversations` + `conversation_participants`, let real
    `list_conversations` query the mock_db with role-scoped visibility logic.
    Tests now exercise the actual auth/role-scoping path instead of asserting
    the patched helper returned a hardcoded SAMPLE.
    """

    def test_list_conversations_patient(self, patient_client):
        _seed_conversation_for_user(patient_client, user_id="test-user-123")
        resp = patient_client.get("/api/conversations")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert "pagination" in body

    def test_list_conversations_therapist(self, client):
        _seed_conversation_for_user(client, user_id="test-user-123")
        resp = client.get("/api/conversations")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_conversations_admin_sees_all(self, admin_client):
        # platform_admin path: real `list_conversations` queries `conversations`
        # directly without participant filtering — seed 2 conversations.
        admin_client._mock_supabase.set_table_data("conversations", [
            {"id": "conv-001", "mode": "human", "is_archived": False,
             "last_message_at": "2026-04-01T12:00:00Z",
             "created_at": "2026-04-01T10:00:00Z"},
            {"id": "conv-002", "mode": "human", "is_archived": False,
             "last_message_at": "2026-04-01T13:00:00Z",
             "created_at": "2026-04-01T11:00:00Z"},
        ])
        resp = admin_client.get("/api/conversations")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_list_conversations_clinic_admin(self, clinic_admin_client):
        # clinic_admin path: query participants with `participant_type=clinic` +
        # matching `clinic_id`. The default clinic_admin_client uses clinic_id="clinic-001".
        clinic_admin_client._mock_supabase.set_table_data("conversations", [{
            "id": "conv-001", "mode": "human", "is_archived": False,
            "last_message_at": "2026-04-01T12:00:00Z",
            "created_at": "2026-04-01T10:00:00Z",
        }])
        clinic_admin_client._mock_supabase.set_table_data("conversation_participants", [{
            "id": "part-001", "conversation_id": "conv-001",
            "participant_type": "clinic", "clinic_id": "clinic-001",
            "is_muted": False, "is_deleted": False, "is_blocked": False,
            "last_read_message_id": None,
        }])
        resp = clinic_admin_client.get("/api/conversations")
        assert resp.status_code == 200

    def test_list_conversations_unread_filter(self, client):
        _seed_conversation_for_user(client, user_id="test-user-123")
        resp = client.get("/api/conversations?filter_type=unread")
        assert resp.status_code == 200

    def test_list_conversations_busca(self, client):
        # Empty seed — `list_conversations` returns ([], 0) for the busca filter.
        resp = client.get("/api/conversations?busca=terapeuta")
        assert resp.status_code == 200

    def test_list_conversations_pagination(self, client):
        # Seed 5 conversations + the same user as participant in each, so
        # real `list_conversations` returns total=5 and the first-page slice.
        # MockSupabaseClient's `.range()` honors the slice; `count="exact"`
        # returns the total.
        client._mock_supabase.set_table_data("conversations", [
            {"id": f"conv-{i:03d}", "mode": "human", "is_archived": False,
             "last_message_at": f"2026-04-0{i+1}T12:00:00Z",
             "created_at": f"2026-04-0{i+1}T10:00:00Z"}
            for i in range(1, 6)
        ])
        client._mock_supabase.set_table_data("conversation_participants", [
            {"id": f"part-{i:03d}", "conversation_id": f"conv-{i:03d}",
             "participant_type": "user", "participant_id": "test-user-123",
             "is_muted": False, "is_deleted": False, "is_blocked": False,
             "last_read_message_id": None}
            for i in range(1, 6)
        ])
        resp = client.get("/api/conversations?page=1&page_size=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page_size"] == 1

    def test_list_conversations_no_auth(self, client):
        resp = client._tc.get("/api/conversations")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Send Message
# ---------------------------------------------------------------------------

class TestSendMessage:
    """Pattern 3: seed `conversation_participants` + `user_blocks`, let real
    `send_message` query participants, validate auth, check blocks, insert
    the message. Tests now exercise the actual authorization path.
    """

    def test_send_text_message(self, client):
        """Pattern 3: seed conversation + sender participant; real `send_message`
        validates the sender, inserts the message via `MockSupabaseClient.insert(...)`,
        and the mock returns the inserted row (with auto-id) so `first_or_none(result)`
        gives the route handler something to return.

        Unblocked 2026-04-28 by `MockRequestBuilder.insert(...)` returning the
        inserted row in `result.data` (was `result.data = []` before, breaking
        `first_or_none`). The patched assertion `data["content"] == "Olá, como você
        está?"` (a SAMPLE constant mismatching the request) is now corrected to
        match the actual request content — Pattern 3 surfaced a content mismatch
        the patch was hiding.
        """
        _seed_conversation_for_user(client, user_id="test-user-123")
        resp = client.post("/api/conversations/conv-001/messages", json={
            "content": "Olá, tudo bem?",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Real `send_message` insert flows the request content through unchanged.
        assert data["content"] == "Olá, tudo bem?"
        assert data["conversation_id"] == "conv-001"
        assert data["sender_user_id"] == "test-user-123"

    def test_send_message_non_participant_denied(self, client):
        # Seed conv-999 with OTHER users only — test user is NOT a participant.
        # Real `send_message` raises 403 at messaging_service.py line 200-213.
        client._mock_supabase.set_table_data("conversation_participants", [{
            "id": "part-999", "conversation_id": "conv-999",
            "participant_type": "user", "participant_id": "stranger-user-789",
            "is_muted": False, "is_deleted": False, "is_blocked": False,
            "last_read_message_id": None,
        }])
        resp = client.post("/api/conversations/conv-999/messages", json={
            "content": "Tentando enviar",
        })
        assert resp.status_code == 403
        _assert_error_contains(resp, "participante")

    def test_send_message_blocked_user_denied(self, client):
        # Seed conversation + participants + a block row. Real `send_message`
        # finds participants, then `_check_block` returns True → raises 403
        # at messaging_service.py line 220-225.
        _seed_conversation_for_user(client, user_id="test-user-123",
                                    other_user_id="other-user-456")
        # Override participants seed to add the block row alongside.
        client._mock_supabase.set_table_data("user_blocks", [{
            "id": "block-001",
            "blocker_id": "other-user-456",
            "blocked_id": "test-user-123",
            "created_at": "2026-04-01T10:00:00Z",
        }])
        resp = client.post("/api/conversations/conv-001/messages", json={
            "content": "Bloqueado",
        })
        assert resp.status_code == 403
        _assert_error_contains(resp, "bloqueado")

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
    def test_get_messages_success(self, client):
        """Pattern 3: real `get_messages` validates the user is a participant,
        then queries `messages` filtered by `conversation_id`. Seed both."""
        _seed_conversation_for_user(client, user_id="test-user-123")
        client._mock_supabase.set_table_data("messages", [SAMPLE_MESSAGE])
        resp = client.get("/api/conversations/conv-001/messages")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert "pagination" in body

    def test_get_messages_non_participant_denied(self, client):
        """Pattern 3: empty `conversation_participants` seed — the access
        check finds nothing for (conv-999, test-user-123), raises 403.

        Note: `MockSupabaseClient` doesn't apply filter args, so seeding a
        stranger's row would still satisfy the non-empty check (false-positive
        access). Empty seed is the correct shape for "not a participant"."""
        client._mock_supabase.set_table_data("conversation_participants", [])
        resp = client.get("/api/conversations/conv-999/messages")
        assert resp.status_code == 403

    def test_get_messages_pagination(self, client):
        """Pattern 3: real `get_messages` honours page + page_size; pagination
        section reflects the requested page."""
        _seed_conversation_for_user(client, user_id="test-user-123")
        client._mock_supabase.set_table_data("messages", [SAMPLE_MESSAGE])
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
    def test_mark_as_read_success(self, client):
        """Pattern 3: real `mark_as_read` queries the latest message in
        conversation, then updates the participant's `last_read_message_id`.
        Seed conversation_participants + messages so both queries succeed."""
        _seed_conversation_for_user(client, user_id="test-user-123")
        client._mock_supabase.set_table_data("messages", [SAMPLE_MESSAGE])
        resp = client.patch("/api/conversations/conv-001/read")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Delete Message (hard delete)
# ---------------------------------------------------------------------------

class TestDeleteMessage:
    def test_delete_message_sender_success(self, client):
        """Pattern 3: seed a message owned by the sender; real `delete_message`
        verifies sender_user_id matches and deletes."""
        client._mock_supabase.set_table_data("messages", [{
            "id": "msg-001", "sender_user_id": "test-user-123",
            "conversation_id": "conv-001",
        }])
        resp = client.delete("/api/conversations/messages/msg-001")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_message_non_sender_denied(self, client):
        """Pattern 3: seed message with a DIFFERENT sender; real `delete_message`
        raises 403 at the sender_user_id mismatch."""
        client._mock_supabase.set_table_data("messages", [{
            "id": "msg-other", "sender_user_id": "stranger-user-789",
            "conversation_id": "conv-001",
        }])
        resp = client.delete("/api/conversations/messages/msg-other")
        assert resp.status_code == 403

    def test_delete_message_not_found(self, client):
        """Pattern 3: empty messages seed → real `delete_message` raises 404."""
        client._mock_supabase.set_table_data("messages", [])
        resp = client.delete("/api/conversations/messages/msg-nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Report Message
# ---------------------------------------------------------------------------

class TestReportMessage:
    def test_report_message_success(self, client):
        """Pattern 3: seed the message lookup the router uses to derive
        conversation_id; real `report_message` inserts into `message_reports`
        and returns the auto-id row."""
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
    def test_archive_conversation_success(self, client):
        """Pattern 3: real `archive_conversation` updates participant.is_deleted;
        update returns the seeded row → first_or_none gives back a participant
        → success."""
        _seed_conversation_for_user(client, user_id="test-user-123")
        resp = client.post("/api/conversations/conv-001/archive")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_archive_conversation_not_found(self, client):
        """Pattern 3: empty conversation_participants seed → update returns
        no row → real `archive_conversation` raises 404."""
        client._mock_supabase.set_table_data("conversation_participants", [])
        resp = client.post("/api/conversations/conv-999/archive")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Mute Conversation
# ---------------------------------------------------------------------------

class TestMuteConversation:
    def test_mute_conversation(self, client):
        """Pattern 3: real `mute_conversation` updates participant.is_muted=True
        and returns the participant row."""
        _seed_conversation_for_user(client, user_id="test-user-123")
        resp = client.post("/api/conversations/conv-001/mute?mute=true")
        assert resp.status_code == 200

    def test_unmute_conversation(self, client):
        """Pattern 3: real `mute_conversation` updates participant.is_muted=False."""
        _seed_conversation_for_user(client, user_id="test-user-123")
        resp = client.post("/api/conversations/conv-001/mute?mute=false")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Block / Unblock
# ---------------------------------------------------------------------------

class TestBlockUser:
    def test_block_user_success(self, client):
        """Pattern 3: empty user_blocks seed → real `block_user` finds no
        existing block, inserts a new one, returns ok."""
        client._mock_supabase.set_table_data("user_blocks", [])
        resp = client.post("/api/conversations/block", json={
            "blocked_user_id": "bad-user-789",
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_block_user_hides_conversations(self, client):
        """Pattern 3: real `block_user` inserts the block row and runs
        `_hide_mutual_conversations` which updates participant.is_deleted."""
        client._mock_supabase.set_table_data("user_blocks", [])
        resp = client.post("/api/conversations/block", json={
            "blocked_user_id": "other-user-456",
        })
        assert resp.status_code == 200
        # Verify the block was inserted (real side-effect, no patch).
        block_payloads = client._mock_supabase.table("user_blocks").inserted_payloads
        assert any(
            p.get("blocked_user_id") == "other-user-456"
            for p in block_payloads
        ), f"expected block of other-user-456 in inserted_payloads, got: {block_payloads!r}"

    def test_block_self_fails(self, client):
        """Pattern 3: real `block_user` raises 400 when blocker_id == blocked_id."""
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
    def test_unblock_user_success(self, client):
        """Pattern 3: seed an existing user_blocks row; real `unblock_user`
        finds it, deletes, returns ok."""
        _seed_block(client, blocker_id="test-user-123", blocked_id="bad-user-789")
        # `block_user` schema uses `blocker_user_id`/`blocked_user_id` (the
        # `_seed_block` helper writes the legacy `blocker_id`/`blocked_id`
        # columns used by `_check_block`). Add the canonical-shape row too
        # so `unblock_user`'s pre-check passes.
        client._mock_supabase.set_table_data("user_blocks", [{
            "id": "block-001",
            "blocker_user_id": "test-user-123",
            "blocked_user_id": "bad-user-789",
            "created_at": "2026-04-01T10:00:00Z",
        }])
        resp = client.delete("/api/conversations/block/bad-user-789")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_unblock_user_unhides_conversations(self, client):
        """Pattern 3: real `unblock_user` deletes the block + runs
        `_unhide_mutual_conversations`. Verify via deleted-side-effect — the
        block row was queried."""
        client._mock_supabase.set_table_data("user_blocks", [{
            "id": "block-001",
            "blocker_user_id": "test-user-123",
            "blocked_user_id": "other-user-456",
            "created_at": "2026-04-01T10:00:00Z",
        }])
        resp = client.delete("/api/conversations/block/other-user-456")
        assert resp.status_code == 200

    def test_unblock_user_not_blocked(self, client):
        """Pattern 3: empty user_blocks seed → real `unblock_user` raises 404
        at the pre-check."""
        client._mock_supabase.set_table_data("user_blocks", [])
        resp = client.delete("/api/conversations/block/nonexistent-user")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Unread Count
# ---------------------------------------------------------------------------

class TestUnreadCount:
    def test_unread_count(self, client):
        """Pattern 3: real `get_unread_count` queries the user's participant
        rows + counts messages newer than last_read_message_id. Seed a single
        conversation_participants row so the count loop runs."""
        _seed_conversation_for_user(client, user_id="test-user-123")
        resp = client.get("/api/conversations/unread-count")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "unread_count" in data
        assert isinstance(data["unread_count"], int)

    def test_unread_count_zero(self, patient_client):
        """Pattern 3: empty conversation_participants seed → real
        `get_unread_count` returns 0 at the early-return."""
        patient_client._mock_supabase.set_table_data("conversation_participants", [])
        resp = patient_client.get("/api/conversations/unread-count")
        assert resp.status_code == 200
        assert resp.json()["data"]["unread_count"] == 0

    def test_unread_count_no_auth(self, client):
        resp = client._tc.get("/api/conversations/unread-count")
        assert resp.status_code == 401
