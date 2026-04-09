"""Tests for notificacoes (notifications) router."""
import pytest
from unittest.mock import patch

from tests.conftest import MockSupabaseClient, MockRequestBuilder


# ── Sample Data ──────────────────────────────────────────────────────

SAMPLE_NOTIFICATION_RAW = {
    "id": "notif-001",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "type": "system",
    "title": "Bem-vindo",
    "message": "Sua conta foi criada com sucesso.",
    "metadata": {"link": "/dashboard"},
    "read": False,
    "created_at": "2026-04-01T10:00:00",
}

SAMPLE_NOTIFICATION_RAW_2 = {
    "id": "notif-002",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "type": "usage_alert",
    "title": "Limite atingido",
    "message": "Voce atingiu 90% do limite.",
    "metadata": None,
    "read": True,
    "created_at": "2026-04-02T10:00:00",
}

SAMPLE_NOTIFICATION_RAW_3 = {
    "id": "notif-003",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "type": "subscription_change",
    "title": "Plano atualizado",
    "message": "Seu plano foi atualizado para Pro.",
    "metadata": {"link": "/planos"},
    "read": False,
    "created_at": "2026-04-03T10:00:00",
}


def _make_core_mock(data=None):
    """Create a MockSupabaseClient to be returned by get_core_client()."""
    mock = MockSupabaseClient(data)
    return mock


# ── GET /api/notificacoes ────────────────────────────────────────────

class TestListarNotificacoes:
    def test_returns_notifications_list(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [SAMPLE_NOTIFICATION_RAW, SAMPLE_NOTIFICATION_RAW_2])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.get("/api/notificacoes")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 2

    def test_maps_fields_to_portuguese(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [SAMPLE_NOTIFICATION_RAW])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.get("/api/notificacoes")
        assert response.status_code == 200
        item = response.json()["data"][0]
        assert item["tipo"] == "system"
        assert item["titulo"] == "Bem-vindo"
        assert item["mensagem"] == "Sua conta foi criada com sucesso."
        assert item["is_read"] is False
        assert item["link"] == "/dashboard"
        assert item["id"] == "notif-001"
        assert item["created_at"] == "2026-04-01T10:00:00"

    def test_maps_none_metadata_link(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [SAMPLE_NOTIFICATION_RAW_2])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.get("/api/notificacoes")
        assert response.status_code == 200
        item = response.json()["data"][0]
        assert item["link"] is None
        assert item["is_read"] is True

    def test_returns_pagination_info(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [SAMPLE_NOTIFICATION_RAW])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.get("/api/notificacoes?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert "pagination" in data
        assert "total" in data["pagination"]
        assert "page" in data["pagination"]
        assert "page_size" in data["pagination"]

    def test_pagination_params(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [SAMPLE_NOTIFICATION_RAW])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.get("/api/notificacoes?page=2&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["page_size"] == 5

    def test_filter_apenas_nao_lidas(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [SAMPLE_NOTIFICATION_RAW])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.get("/api/notificacoes?apenas_nao_lidas=true")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["data"], list)

    def test_empty_list(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.get("/api/notificacoes")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["pagination"]["total"] == 0

    def test_requires_auth(self, client):
        response = client._tc.get("/api/notificacoes")
        assert response.status_code == 401


# ── GET /api/notificacoes/contagem ───────────────────────────────────

class TestContagemNaoLidas:
    def test_returns_unread_count(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [SAMPLE_NOTIFICATION_RAW, SAMPLE_NOTIFICATION_RAW_3])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.get("/api/notificacoes/contagem")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "nao_lidas" in data["data"]

    def test_returns_zero_when_no_unread(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.get("/api/notificacoes/contagem")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["nao_lidas"] == 0

    def test_requires_auth(self, client):
        response = client._tc.get("/api/notificacoes/contagem")
        assert response.status_code == 401


# ── PATCH /api/notificacoes/{id}/ler ─────────────────────────────────

class TestMarcarComoLida:
    def test_marks_notification_as_read(self, client):
        updated = {**SAMPLE_NOTIFICATION_RAW, "read": True}
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [updated])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.patch("/api/notificacoes/notif-001/ler")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["is_read"] is True
        assert data["data"]["id"] == "notif-001"

    def test_maps_response_to_portuguese(self, client):
        updated = {**SAMPLE_NOTIFICATION_RAW, "read": True}
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [updated])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.patch("/api/notificacoes/notif-001/ler")
        assert response.status_code == 200
        item = response.json()["data"]
        assert "tipo" in item
        assert "titulo" in item
        assert "mensagem" in item
        assert "is_read" in item
        assert "link" in item

    def test_not_found_returns_404(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.patch("/api/notificacoes/nonexistent-id/ler")
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/notificacoes/notif-001/ler")
        assert response.status_code == 401


# ── POST /api/notificacoes/ler-todas ─────────────────────────────────

class TestMarcarTodasComoLidas:
    def test_marks_all_as_read(self, client):
        updated = [
            {**SAMPLE_NOTIFICATION_RAW, "read": True},
            {**SAMPLE_NOTIFICATION_RAW_3, "read": True},
        ]
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", updated)
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.post("/api/notificacoes/ler-todas")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "2" in data["message"]

    def test_returns_zero_when_none_unread(self, client):
        core_mock = _make_core_mock()
        core_mock.set_table_data("notifications", [])
        with patch("app.routers.notificacoes.get_core_client", return_value=core_mock):
            response = client.post("/api/notificacoes/ler-todas")
        assert response.status_code == 200
        data = response.json()
        assert "0" in data["message"]

    def test_requires_auth(self, client):
        response = client._tc.post("/api/notificacoes/ler-todas")
        assert response.status_code == 401
