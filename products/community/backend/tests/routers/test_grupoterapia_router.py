"""Tests for `grupoterapia_router` — contract §Grupoterapia, staff side."""
from tests.conftest import ORG_UUID, seed_community_role

SESSAO_1 = "22222222-2222-2222-2222-222222222222"
MEMBRO_1 = "44444444-4444-4444-4444-444444444444"


def _sessao_row(**over) -> dict:
    base = {
        "id": SESSAO_1,
        "org_id": ORG_UUID,
        "titulo": "Roda de acolhimento",
        "descricao": None,
        "inicio": "2026-10-01T19:00:00+00:00",
        "duracao_minutos": 90,
        "link_sala": "https://meet.example/roda",
        "vagas_fala": 8,
        "status": "agendada",
        "criado_por": None,
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    base.update(over)
    return base


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/grupoterapia/sessoes").status_code == 401

    def test_create_without_auth_401(self, client):
        assert client.raw().post("/api/grupoterapia/sessoes", json={}).status_code == 401

    def test_update_without_auth_401(self, client):
        resp = client.raw().patch(f"/api/grupoterapia/sessoes/{SESSAO_1}", json={})
        assert resp.status_code == 401

    def test_delete_without_auth_401(self, client):
        assert client.raw().delete(f"/api/grupoterapia/sessoes/{SESSAO_1}").status_code == 401

    def test_reservas_without_auth_401(self, client):
        resp = client.raw().get(f"/api/grupoterapia/sessoes/{SESSAO_1}/reservas")
        assert resp.status_code == 401


class TestRoleGate:
    def test_moderador_can_list(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.get("/api/grupoterapia/sessoes").status_code == 200

    def test_moderador_create_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post("/api/grupoterapia/sessoes", json={
            "titulo": "X", "inicio": "2026-10-01T19:00:00+00:00",
        })
        assert resp.status_code == 403
        assert resp.json()["detail"].startswith("Apenas administradores podem")

    def test_moderador_update_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.patch(f"/api/grupoterapia/sessoes/{SESSAO_1}", json={"vagas_fala": 1})
        assert resp.status_code == 403

    def test_moderador_delete_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.delete(f"/api/grupoterapia/sessoes/{SESSAO_1}")
        assert resp.status_code == 403


class TestCrud:
    def test_create_201(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post("/api/grupoterapia/sessoes", json={
            "titulo": "Nova sessão", "inicio": "2026-11-01T19:00:00+00:00",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "agendada"
        assert body["duracao_minutos"] == 90
        assert body["vagas_fala"] == 8
        assert body["reservas"] == 0

    def test_list_200(self, client):
        client.mock_supabase.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        resp = client.get("/api/grupoterapia/sessoes")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_update_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.patch("/api/grupoterapia/sessoes/does-not-exist", json={"vagas_fala": 1})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Sessão não encontrada."

    def test_delete_404(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupoterapia_sessoes", [])
        resp = client.delete("/api/grupoterapia/sessoes/does-not-exist")
        assert resp.status_code == 404

    def test_delete_204(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        client.mock_supabase.set_table_data("grupoterapia_reservas", [])
        resp = client.delete(f"/api/grupoterapia/sessoes/{SESSAO_1}")
        assert resp.status_code == 204

    def test_delete_409_with_reservations(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        client.mock_supabase.set_table_data("grupoterapia_reservas", [{
            "id": "r1", "org_id": ORG_UUID, "sessao_id": SESSAO_1,
            "membro_id": MEMBRO_1, "status": "confirmada",
        }])
        resp = client.delete(f"/api/grupoterapia/sessoes/{SESSAO_1}")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Sessão com reservas — cancele em vez de excluir."

    def test_cancel_writes_evento_per_confirmed_reserva(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("grupoterapia_sessoes", [_sessao_row()])
        client.mock_supabase.set_table_data("grupoterapia_reservas", [{
            "id": "r1", "org_id": ORG_UUID, "sessao_id": SESSAO_1,
            "membro_id": MEMBRO_1, "status": "confirmada",
        }])
        resp = client.patch(
            f"/api/grupoterapia/sessoes/{SESSAO_1}", json={"status": "cancelada"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelada"
        eventos = client.mock_supabase.table("membro_eventos").select("*").execute().data
        assert len(eventos) == 1
        assert eventos[0]["tipo"] == "grupoterapia"

    def test_reservas_200(self, client):
        client.mock_supabase.set_table_data("membros", [
            {"id": MEMBRO_1, "org_id": ORG_UUID, "nome": "Ana"},
        ])
        client.mock_supabase.set_table_data("grupoterapia_reservas", [{
            "id": "66666666-6666-6666-6666-666666666666", "org_id": ORG_UUID,
            "sessao_id": SESSAO_1, "membro_id": MEMBRO_1, "status": "confirmada",
            "created_at": "2026-09-02T00:00:00+00:00",
        }])
        resp = client.get(f"/api/grupoterapia/sessoes/{SESSAO_1}/reservas")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["membro_nome"] == "Ana"
