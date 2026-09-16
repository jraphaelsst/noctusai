"""Tests for `membros_router` — contract §Membros."""
from tests.conftest import ORG_UUID, seed_community_role

PLANO_1 = "11111111-1111-1111-1111-111111111111"
MEMBRO_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MEMBRO_2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
MEMBRO_3 = "cccccccc-cccc-cccc-cccc-cccccccccccc"
UNKNOWN_ID = "99999999-9999-9999-9999-999999999999"


def _membro_row(**over) -> dict:
    base = {
        "id": MEMBRO_1,
        "org_id": ORG_UUID,
        "nome": "Ana",
        "email": "ana@x.com",
        "telefone": None,
        "status": "ativo",
        "plano_id": None,
        "origem": "checkout",
        "tags": [],
        "user_id": None,
        "observacoes": None,
        "entrou_em": "2026-09-16T20:00:00+00:00",
        "created_at": "2026-09-16T20:00:00+00:00",
        "updated_at": "2026-09-16T20:00:00+00:00",
    }
    base.update(over)
    return base


class TestMembrosAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/membros").status_code == 401

    def test_create_without_auth_401(self, client):
        assert client.raw().post("/api/membros", json={}).status_code == 401

    def test_get_without_auth_401(self, client):
        assert client.raw().get(f"/api/membros/{MEMBRO_1}").status_code == 401

    def test_update_without_auth_401(self, client):
        assert client.raw().patch(f"/api/membros/{MEMBRO_1}", json={}).status_code == 401

    def test_status_without_auth_401(self, client):
        resp = client.raw().post(f"/api/membros/{MEMBRO_1}/status", json={"status": "ativo"})
        assert resp.status_code == 401

    def test_delete_without_auth_401(self, client):
        assert client.raw().delete(f"/api/membros/{MEMBRO_1}").status_code == 401


class TestMembrosRoleGate:
    def test_moderador_can_read(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.get("/api/membros").status_code == 200

    def test_moderador_create_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post("/api/membros", json={
            "nome": "X", "email": "x@x.com", "origem": "checkout",
        })
        assert resp.status_code == 403
        assert resp.json()["detail"].startswith("Apenas administradores podem")

    def test_moderador_status_change_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/membros/{MEMBRO_1}/status", json={"status": "pausado"})
        assert resp.status_code == 403

    def test_moderador_delete_403(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.delete(f"/api/membros/{MEMBRO_1}").status_code == 403


class TestMembrosCrud:
    def test_create_201(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post("/api/membros", json={
            "nome": "Ana", "email": "ana@x.com", "origem": "checkout",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "pendente"
        assert body["origem"] == "checkout"

    def test_create_duplicate_email_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row(email="dup@x.com")])
        resp = client.post("/api/membros", json={
            "nome": "Outra", "email": "dup@x.com", "origem": "checkout",
        })
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Já existe um membro com esse e-mail."

    def test_get_200(self, client):
        client.mock_supabase.set_table_data("membros", [_membro_row()])
        resp = client.get(f"/api/membros/{MEMBRO_1}")
        assert resp.status_code == 200
        assert resp.json()["id"] == MEMBRO_1

    def test_get_404(self, client):
        resp = client.get(f"/api/membros/{UNKNOWN_ID}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Membro não encontrado."

    def test_plano_nome_denormalized(self, client):
        client.mock_supabase.set_table_data("planos", [{
            "id": PLANO_1, "org_id": ORG_UUID, "nome": "Círculo",
            "preco_centavos": 9900, "ciclo": "mensal", "entitlements": {},
            "ativo": True, "ordem": 0,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        client.mock_supabase.set_table_data("membros", [_membro_row(plano_id=PLANO_1)])
        resp = client.get(f"/api/membros/{MEMBRO_1}")
        assert resp.status_code == 200
        assert resp.json()["plano_nome"] == "Círculo"

    def test_list_status_csv_filter_and_resumo_ignores_status(self, client):
        client.mock_supabase.set_table_data("membros", [
            _membro_row(id=MEMBRO_1, nome="Ana", status="ativo"),
            _membro_row(id=MEMBRO_2, nome="Bruna", status="atrasado"),
            _membro_row(id=MEMBRO_3, nome="Carla", status="cancelado"),
        ])
        resp = client.get("/api/membros", params={"status": "ativo,atrasado"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert {item["id"] for item in body["items"]} == {MEMBRO_1, MEMBRO_2}
        # resumo counts the WHOLE org regardless of the status filter.
        assert body["resumo"] == {
            "pendente": 0, "ativo": 1, "atrasado": 1, "pausado": 0, "cancelado": 1,
        }

    def test_list_busca_matches_nome_or_email_case_insensitive(self, client):
        client.mock_supabase.set_table_data("membros", [
            _membro_row(id=MEMBRO_1, nome="Ana Paula", email="ana@x.com"),
            _membro_row(id=MEMBRO_2, nome="Bruna", email="BRUNA@EXAMPLE.com"),
        ])
        resp = client.get("/api/membros", params={"busca": "bruna"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == MEMBRO_2

    def test_list_ordered_by_nome(self, client):
        client.mock_supabase.set_table_data("membros", [
            _membro_row(id=MEMBRO_2, nome="Zeta"),
            _membro_row(id=MEMBRO_1, nome="Alfa"),
        ])
        resp = client.get("/api/membros")
        assert resp.status_code == 200
        assert [i["id"] for i in resp.json()["items"]] == [MEMBRO_1, MEMBRO_2]

    def test_update_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row()])
        resp = client.patch(f"/api/membros/{MEMBRO_1}", json={"observacoes": "VIP"})
        assert resp.status_code == 200
        assert resp.json()["observacoes"] == "VIP"

    def test_update_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.patch(f"/api/membros/{UNKNOWN_ID}", json={"observacoes": "x"})
        assert resp.status_code == 404

    def test_status_change_idempotent_same_status_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row(status="ativo", plano_id=PLANO_1)])
        resp = client.post(f"/api/membros/{MEMBRO_1}/status", json={"status": "ativo"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ativo"

    def test_status_change_to_ativo_without_plano_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row(status="pendente", plano_id=None)])
        resp = client.post(f"/api/membros/{MEMBRO_1}/status", json={"status": "ativo"})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Defina um plano antes de ativar o membro."

    def test_status_change_to_ativo_with_plano_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row(status="pendente", plano_id=PLANO_1)])
        resp = client.post(f"/api/membros/{MEMBRO_1}/status", json={"status": "ativo"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ativo"

    def test_status_change_invalid_value_422(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row()])
        resp = client.post(f"/api/membros/{MEMBRO_1}/status", json={"status": "invalido"})
        assert resp.status_code == 422

    def test_status_change_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post(f"/api/membros/{UNKNOWN_ID}/status", json={"status": "ativo"})
        assert resp.status_code == 404

    def test_delete_204_sets_cancelado_never_hard_deletes(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("membros", [_membro_row(status="ativo")])
        resp = client.delete(f"/api/membros/{MEMBRO_1}")
        assert resp.status_code == 204
        # The row still exists (soft-delete) — a follow-up GET still finds it.
        get_resp = client.get(f"/api/membros/{MEMBRO_1}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "cancelado"

    def test_delete_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.delete(f"/api/membros/{UNKNOWN_ID}")
        assert resp.status_code == 404
