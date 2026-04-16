"""
Tests for the Notificacoes Router — list, count, mark read, mark all read.

The notifications router is now provided by the noctusai_seed framework.
We patch the DatabaseModule methods to mock database access.
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
    "is_read": False,
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_NOTIFICATION_READ = {
    **SAMPLE_NOTIFICATION,
    "id": "notif-002",
    "title": "Sessão confirmada",
    "message": "Sua sessão foi confirmada",
    "is_read": True,
}


# ---------------------------------------------------------------------------
# Fixture — uses seed framework patching
# ---------------------------------------------------------------------------

@pytest.fixture
def notif_client():
    """Client with DatabaseModule methods mocked."""
    mock_sb = MockSupabaseClient()
    mock_core = MockSupabaseClient()
    mock_user = MockUser(role="therapist")
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(mock_user))

    p1 = patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb)
    p2 = patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_core)
    p3 = patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb)
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

    def test_list_notificacoes_empty(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [])
        resp = notif_client.get("/api/notificacoes")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_notificacoes_pagination(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [SAMPLE_NOTIFICATION])
        resp = notif_client.get("/api/notificacoes?page=1&page_size=5")
        assert resp.status_code == 200
        assert resp.json()["page_size"] == 5

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
        body = resp.json()
        assert "nao_lidas" in body
        assert isinstance(body["nao_lidas"], int)

    def test_contagem_no_unread(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [])
        resp = notif_client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        assert resp.json()["nao_lidas"] == 0

    def test_contagem_no_auth(self, notif_client):
        resp = notif_client._tc.get("/api/notificacoes/contagem")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Mark Read
# ---------------------------------------------------------------------------

class TestMarcarComoLida:
    def test_mark_single_read(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [
            {**SAMPLE_NOTIFICATION, "is_read": True},
        ])
        resp = notif_client.patch("/api/notificacoes/notif-001/ler")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_mark_read_no_auth(self, notif_client):
        resp = notif_client._tc.patch("/api/notificacoes/notif-001/ler")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Mark All Read
# ---------------------------------------------------------------------------

class TestMarcarTodasComoLidas:
    def test_mark_all_read(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [
            {**SAMPLE_NOTIFICATION, "is_read": True},
            {**SAMPLE_NOTIFICATION, "id": "notif-003", "is_read": True},
        ])
        resp = notif_client.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_mark_all_read_none_unread(self, notif_client):
        notif_client._mock_core.set_table_data("notifications", [])
        resp = notif_client.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 200

    def test_mark_all_read_no_auth(self, notif_client):
        resp = notif_client._tc.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 401
