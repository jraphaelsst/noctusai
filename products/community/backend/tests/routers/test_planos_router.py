"""Tests for `planos_router` — contract §Planos.

Auth boundary asserts strict `== 401` (never `in (401, 404|422)`). Role
gate (`moderador` reads-only / `admin` writes) asserts the contract's
pt-BR 403 message shape (`"Apenas administradores podem …"`).
"""
from tests.conftest import ORG_UUID, seed_community_role

PLANO_1 = "11111111-1111-1111-1111-111111111111"
PLANO_2 = "22222222-2222-2222-2222-222222222222"
PLANO_3 = "33333333-3333-3333-3333-333333333333"
MEMBRO_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MEMBRO_2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
UNKNOWN_ID = "99999999-9999-9999-9999-999999999999"


def _plano_row(**over) -> dict:
    base = {
        "id": PLANO_1,
        "org_id": ORG_UUID,
        "nome": "Círculo",
        "descricao": None,
        "preco_centavos": 9900,
        "ciclo": "mensal",
        "entitlements": {
            "feed": True, "forum": True, "chat": True, "eventos": True,
            "conteudo_ids": [], "grupos_whatsapp": [], "conteudo_todos": False,
        },
        "ativo": True,
        "ordem": 0,
        "created_at": "2026-09-16T20:00:00+00:00",
        "updated_at": "2026-09-16T20:00:00+00:00",
    }
    base.update(over)
    return base


def _membro_row(**over) -> dict:
    base = {
        "id": MEMBRO_1,
        "org_id": ORG_UUID,
        "nome": "A",
        "email": "a@x.com",
        "telefone": None,
        "status": "ativo",
        "plano_id": PLANO_1,
        "plano_nome": None,
        "origem": "checkout",
        "tags": [],
        "user_id": None,
        "observacoes": None,
        "entrou_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


class TestPlanosAuthBoundary:
    def test_list_without_auth_401(self, client):
        resp = client.raw().get("/api/planos")
        assert resp.status_code == 401

    def test_create_without_auth_401(self, client):
        resp = client.raw().post("/api/planos", json={})
        assert resp.status_code == 401

    def test_get_without_auth_401(self, client):
        resp = client.raw().get(f"/api/planos/{PLANO_1}")
        assert resp.status_code == 401

    def test_update_without_auth_401(self, client):
        resp = client.raw().patch(f"/api/planos/{PLANO_1}", json={})
        assert resp.status_code == 401

    def test_delete_without_auth_401(self, client):
        resp = client.raw().delete(f"/api/planos/{PLANO_1}")
        assert resp.status_code == 401


class TestPlanosRoleGate:
    """Reads allow admin+moderador; writes are admin-only → 403."""

    def test_moderador_can_read(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.get("/api/planos")
        assert resp.status_code == 200

    def test_moderador_create_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post("/api/planos", json={
            "nome": "Novo", "preco_centavos": 100, "ciclo": "mensal",
        })
        assert resp.status_code == 403
        assert resp.json()["detail"].startswith("Apenas administradores podem")

    def test_moderador_update_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.patch(f"/api/planos/{PLANO_1}", json={"nome": "X"})
        assert resp.status_code == 403

    def test_moderador_delete_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.delete(f"/api/planos/{PLANO_1}")
        assert resp.status_code == 403

    def test_default_role_with_no_noctus_users_row_is_moderador(self, client):
        # No seed_community_role call — the plain default. Reads still work,
        # writes still 403 (least-privileged default).
        resp = client.post("/api/planos", json={
            "nome": "Novo", "preco_centavos": 100, "ciclo": "mensal",
        })
        assert resp.status_code == 403


class TestPlanosCrud:
    def test_create_201_and_membros_ativos_zero(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post("/api/planos", json={
            "nome": "Círculo", "preco_centavos": 9900, "ciclo": "mensal",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["nome"] == "Círculo"
        assert body["membros_ativos"] == 0
        assert body["entitlements"]["feed"] is False

    def test_create_duplicate_nome_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("planos", [_plano_row()])
        resp = client.post("/api/planos", json={
            "nome": "Círculo", "preco_centavos": 100, "ciclo": "mensal",
        })
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Já existe um plano com esse nome."

    def test_list_200_ordered_by_ordem_then_nome(self, client):
        client.mock_supabase.set_table_data("planos", [
            _plano_row(id=PLANO_2, nome="Zeta", ordem=1),
            _plano_row(id=PLANO_1, nome="Alfa", ordem=0),
            _plano_row(id=PLANO_3, nome="Beta", ordem=1),
        ])
        resp = client.get("/api/planos")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert [item["id"] for item in body["items"]] == [PLANO_1, PLANO_3, PLANO_2]

    def test_list_filters_by_ativo(self, client):
        client.mock_supabase.set_table_data("planos", [
            _plano_row(id=PLANO_1, ativo=True),
            _plano_row(id=PLANO_2, nome="Outro", ativo=False),
        ])
        resp = client.get("/api/planos", params={"ativo": "true"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == PLANO_1

    def test_get_200(self, client):
        client.mock_supabase.set_table_data("planos", [_plano_row()])
        resp = client.get(f"/api/planos/{PLANO_1}")
        assert resp.status_code == 200
        assert resp.json()["id"] == PLANO_1

    def test_get_404(self, client):
        resp = client.get(f"/api/planos/{UNKNOWN_ID}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Plano não encontrado."

    def test_membros_ativos_counts_active_members_only(self, client):
        client.mock_supabase.set_table_data("planos", [_plano_row()])
        client.mock_supabase.set_table_data("membros", [
            _membro_row(id=MEMBRO_1, status="ativo"),
            _membro_row(id=MEMBRO_2, status="cancelado"),
        ])
        resp = client.get(f"/api/planos/{PLANO_1}")
        assert resp.status_code == 200
        assert resp.json()["membros_ativos"] == 1

    def test_update_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("planos", [_plano_row()])
        resp = client.patch(f"/api/planos/{PLANO_1}", json={"preco_centavos": 12900})
        assert resp.status_code == 200
        assert resp.json()["preco_centavos"] == 12900

    def test_update_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.patch(f"/api/planos/{UNKNOWN_ID}", json={"nome": "X"})
        assert resp.status_code == 404

    def test_delete_204_soft_delete(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("planos", [_plano_row()])
        resp = client.delete(f"/api/planos/{PLANO_1}")
        assert resp.status_code == 204

    def test_delete_still_204_when_members_reference_it(self, client):
        """Contract: soft-delete never blocks on existing member refs."""
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("planos", [_plano_row()])
        client.mock_supabase.set_table_data("membros", [_membro_row()])
        resp = client.delete(f"/api/planos/{PLANO_1}")
        assert resp.status_code == 204

    def test_delete_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.delete(f"/api/planos/{UNKNOWN_ID}")
        assert resp.status_code == 404
