"""Tests for the notifications (notificacoes) router — provided by seed framework."""
from noctusai_lib.testing import MockSupabaseResponse


MOCK_NOTIFICATION = {
    "id": "notif-001",
    "user_id": "test-user-123",  # must match MockUser.id default
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

    def test_list_no_auth(self, client):
        resp = client.raw().get("/api/notificacoes")
        assert resp.status_code == 401


class TestContagem:
    """GET /api/notificacoes/contagem"""

    def test_contagem(self, client):
        # `.eq("user_id", ...).eq("read", False)` — both keys are required
        # (mock's `count="exact"` reflects the filtered rows, not len(table);
        # fixed 2026-09-16).
        client.mock_supabase.set_table_data("notifications", [
            {"id": "n1", "user_id": "test-user-123", "read": False},
            {"id": "n2", "user_id": "test-user-123", "read": False},
            {"id": "n3", "user_id": "test-user-123", "read": False},
        ])
        resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nao_lidas"] == 3


class TestMarcarLida:
    """PATCH /api/notificacoes/{id}/ler"""

    def test_marcar_lida(self, client):
        read_notif = {**MOCK_NOTIFICATION, "read": True}
        client.mock_supabase.set_table_data("notifications", [read_notif])
        resp = client.patch("/api/notificacoes/notif-001/ler")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True


class TestMarcarTodasLidas:
    """POST /api/notificacoes/ler-todas"""

    def test_marcar_todas(self, client):
        client.mock_supabase.set_table_data("notifications", [MOCK_NOTIFICATION])
        resp = client.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
