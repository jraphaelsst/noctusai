"""
Tests for the Notificacoes Router — list, count, mark read, mark all read.

This router uses get_core_client() to access the public.notifications table,
so we patch "app.routers.notificacoes.get_core_client" instead of the usual
database module.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from tests.conftest import (
    MockSupabaseClient,
    MockSelectBuilder,
    MockUser,
    MockUserResponse,
    AuthClient,
)


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_NOTIFICATION = {
    "id": "notif-001",
    "user_id": "test-user-123",
    "org_id": None,
    "type": "system",
    "title": "Bem vindo!",
    "message": "Sua conta foi criada com sucesso",
    "metadata": {"link": "/dashboard"},
    "read": False,
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_NOTIFICATION_READ = {
    **SAMPLE_NOTIFICATION,
    "id": "notif-002",
    "title": "Sessão confirmada",
    "message": "Sua sessão foi confirmada",
    "read": True,
}


# ---------------------------------------------------------------------------
# Fixture override — notificacoes router needs a separate core_client mock
# ---------------------------------------------------------------------------

@pytest.fixture
def notif_client():
    """Client with both supabase and core_client mocked."""
    mock_sb = MockSupabaseClient()
    mock_core = MockSupabaseClient()
    mock_user = MockUser(role="therapist")
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(mock_user))

    p1 = patch("app.dependencies.get_supabase_client", return_value=mock_sb)
    p2 = patch("app.database.get_supabase_client", return_value=mock_sb)
    p3 = patch("app.routers.notificacoes.get_core_client", return_value=mock_core)
    p1.start()
    p2.start()
    p3.start()

    from app.main import app
    tc = TestClient(app)
    client = AuthClient(tc, mock_sb)
    # Expose the core mock for test setup
    client._mock_core = mock_core
    yield client

    p3.stop()
    p2.stop()
    p1.stop()


# ---------------------------------------------------------------------------
# List Notifications
# ---------------------------------------------------------------------------

class TestListNotificacoes:
    def test_list_notificacoes(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [
            SAMPLE_NOTIFICATION,
            SAMPLE_NOTIFICATION_READ,
        ])
        resp = notif_client.get("/api/notificacoes")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert "pagination" in body
        # Verify field mapping to Portuguese
        item = body["data"][0]
        assert "titulo" in item
        assert "mensagem" in item
        assert "tipo" in item
        assert "is_read" in item

    def test_list_notificacoes_empty(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [])
        resp = notif_client.get("/api/notificacoes")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_notificacoes_unread_only(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [SAMPLE_NOTIFICATION])
        resp = notif_client.get("/api/notificacoes?apenas_nao_lidas=true")
        assert resp.status_code == 200

    def test_list_notificacoes_pagination(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [SAMPLE_NOTIFICATION])
        resp = notif_client.get("/api/notificacoes?page=1&page_size=5")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page_size"] == 5

    def test_list_notificacoes_no_auth(self, notif_client):
        resp = notif_client._tc.get("/api/notificacoes")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Count Unread
# ---------------------------------------------------------------------------

class TestContagemNotificacoes:
    def test_contagem_unread(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [
            SAMPLE_NOTIFICATION,
            {**SAMPLE_NOTIFICATION, "id": "notif-003"},
        ])
        resp = notif_client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "nao_lidas" in data
        assert isinstance(data["nao_lidas"], int)

    def test_contagem_no_unread(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [])
        resp = notif_client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        assert resp.json()["data"]["nao_lidas"] == 0

    def test_contagem_no_auth(self, notif_client):
        resp = notif_client._tc.get("/api/notificacoes/contagem")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Mark Read
# ---------------------------------------------------------------------------

class TestMarcarComoLida:
    def test_mark_single_read(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [
            {**SAMPLE_NOTIFICATION, "read": True},
        ])
        resp = notif_client.patch("/api/notificacoes/notif-001/ler")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_read"] is True

    def test_mark_nonexistent_not_found(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [])
        resp = notif_client.patch("/api/notificacoes/nonexistent/ler")
        assert resp.status_code == 404

    def test_mark_read_no_auth(self, notif_client):
        resp = notif_client._tc.patch("/api/notificacoes/notif-001/ler")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Mark All Read
# ---------------------------------------------------------------------------

class TestMarcarTodasComoLidas:
    def test_mark_all_read(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [
            {**SAMPLE_NOTIFICATION, "read": True},
            {**SAMPLE_NOTIFICATION, "id": "notif-003", "read": True},
        ])
        resp = notif_client.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "marcadas como lidas" in body["message"]

    def test_mark_all_read_none_unread(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [])
        resp = notif_client.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 200
        assert "0 notificações marcadas" in resp.json()["message"]

    def test_mark_all_read_no_auth(self, notif_client):
        resp = notif_client._tc.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 401
