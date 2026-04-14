"""Tests for the notifications (notificacoes) router."""
from noctusai_shared.testing import MockSupabaseResponse


MOCK_NOTIFICATION = {
    "id": "notif-001",
    "user_id": "test-user-id",
    "type": "system",
    "title": "Bem-vindo",
    "message": "Sua conta foi criada",
    "read": False,
    "metadata": {"link": "/dashboard"},
    "created_at": "2026-01-01T00:00:00Z",
}


class TestListNotificacoes:
    """GET /api/notificacoes"""

    def test_list_notificacoes(self, client):
        client.mock_supabase.set_table_data("notifications", [MOCK_NOTIFICATION])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200
        body = resp.json()
        items = body["data"]
        assert len(items) == 1
        # Verify Portuguese field mapping
        item = items[0]
        assert item["tipo"] == "system"
        assert item["titulo"] == "Bem-vindo"
        assert item["mensagem"] == "Sua conta foi criada"
        assert item["is_read"] is False
        assert item["link"] == "/dashboard"

    def test_list_no_auth(self, client):
        resp = client.raw().get("/api/notificacoes")
        assert resp.status_code == 401


class TestContagem:
    """GET /api/notificacoes/contagem"""

    def test_contagem(self, client):
        # select("id", count="exact") — mock 3 items so count == 3
        client.mock_supabase.set_table_data("notifications", [
            {"id": "n1"}, {"id": "n2"}, {"id": "n3"},
        ])
        resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["nao_lidas"] == 3


class TestMarcarLida:
    """PATCH /api/notificacoes/{id}/ler"""

    def test_marcar_lida(self, client):
        read_notif = {**MOCK_NOTIFICATION, "read": True}
        client.mock_supabase.set_table_data("notifications", [read_notif])
        resp = client.patch("/api/notificacoes/notif-001/ler")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["is_read"] is True

    def test_marcar_lida_not_found(self, client):
        client.mock_supabase.set_table_data("notifications", [])
        resp = client.patch("/api/notificacoes/nonexistent/ler")
        assert resp.status_code == 404
