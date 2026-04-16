"""Tests for notificacoes router — provided by seed framework."""
from noctusai_lib.testing import MockSupabaseResponse


MOCK_NOTIFICATION = {
    "id": "notif-001",
    "user_id": "test-user-id",
    "type": "system",
    "title": "Bem-vindo",
    "message": "Sua conta foi criada",
    "read": False,
    "metadata": {},
    "created_at": "2026-01-01T00:00:00Z",
}


class TestListNotificacoes:
    def test_list(self, client):
        client.mock_supabase.set_table_data("notifications", [MOCK_NOTIFICATION])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_no_auth(self, client):
        resp = client.raw().get("/api/notificacoes")
        assert resp.status_code == 401


class TestContagem:
    def test_contagem(self, client):
        client.mock_supabase.set_table_data("notifications", [{"id": "n1"}])
        resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        assert resp.json()["nao_lidas"] == 1


class TestMarcarLida:
    def test_marcar_lida(self, client):
        client.mock_supabase.set_table_data("notifications", [MOCK_NOTIFICATION])
        resp = client.patch("/api/notificacoes/notif-001/ler")
        assert resp.status_code == 200
