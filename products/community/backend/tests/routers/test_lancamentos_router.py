"""Tests for `lancamentos_router` — CONTRACT.md §Cashflow + dashboard,
slice BE-C.
"""
from noctusai_lib.primitives.timeutil import frozen_time
from datetime import datetime, timezone

from tests.conftest import ORG_UUID, seed_community_role

MEMBRO_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LANCAMENTO_1 = "11111111-1111-1111-1111-111111111111"
LANCAMENTO_2 = "22222222-2222-2222-2222-222222222222"
UNKNOWN_ID = "99999999-9999-9999-9999-999999999999"

_NOW = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _lancamento_row(**over) -> dict:
    base = {
        "id": LANCAMENTO_1,
        "org_id": ORG_UUID,
        "tipo": "entrada",
        "categoria": "assinatura",
        "descricao": "Mensalidade Ana",
        "valor_centavos": 2700,
        "data": "2026-06-10",
        "origem": "manual",
        "pagamento_id": None,
        "estorno_de": None,
        "membro_id": None,
        "criado_por": None,
        "created_at": "2026-06-10T00:00:00+00:00",
        "updated_at": "2026-06-10T00:00:00+00:00",
    }
    base.update(over)
    return base


class TestLancamentosAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/lancamentos").status_code == 401

    def test_categorias_without_auth_401(self, client):
        assert client.raw().get("/api/lancamentos/categorias").status_code == 401

    def test_create_without_auth_401(self, client):
        assert client.raw().post("/api/lancamentos", json={}).status_code == 401

    def test_update_without_auth_401(self, client):
        resp = client.raw().patch(f"/api/lancamentos/{LANCAMENTO_1}", json={})
        assert resp.status_code == 401

    def test_delete_without_auth_401(self, client):
        assert client.raw().delete(f"/api/lancamentos/{LANCAMENTO_1}").status_code == 401


class TestLancamentosRoleGate:
    def test_moderador_can_read(self, client):
        seed_community_role(client, org_role="moderador")
        with frozen_time(_NOW):
            assert client.get("/api/lancamentos").status_code == 200

    def test_moderador_create_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post("/api/lancamentos", json={
            "tipo": "entrada", "categoria": "outros",
            "valor_centavos": 100, "data": "2026-06-10",
        })
        assert resp.status_code == 403
        assert resp.json()["detail"].startswith("Apenas administradores podem")

    def test_moderador_update_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.patch(f"/api/lancamentos/{LANCAMENTO_1}", json={"categoria": "outros"})
        assert resp.status_code == 403

    def test_moderador_delete_403(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.delete(f"/api/lancamentos/{LANCAMENTO_1}").status_code == 403


class TestLancamentosCrud:
    def test_create_201_forces_origem_manual(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post("/api/lancamentos", json={
            "tipo": "saida", "categoria": "plataforma", "descricao": "Hospedagem",
            "valor_centavos": 5000, "data": "2026-06-05",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["origem"] == "manual"
        assert body["tipo"] == "saida"
        assert body["valor_centavos"] == 5000

    def test_create_valor_zero_422(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post("/api/lancamentos", json={
            "tipo": "entrada", "categoria": "outros",
            "valor_centavos": 0, "data": "2026-06-05",
        })
        assert resp.status_code == 422

    def test_update_manual_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("lancamentos", [_lancamento_row()])
        resp = client.patch(f"/api/lancamentos/{LANCAMENTO_1}", json={"categoria": "marketing"})
        assert resp.status_code == 200
        assert resp.json()["categoria"] == "marketing"

    def test_update_automatico_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data(
            "lancamentos", [_lancamento_row(origem="pagamento")],
        )
        resp = client.patch(f"/api/lancamentos/{LANCAMENTO_1}", json={"categoria": "marketing"})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Lançamentos automáticos não podem ser alterados."

    def test_update_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.patch(f"/api/lancamentos/{UNKNOWN_ID}", json={"categoria": "marketing"})
        assert resp.status_code == 404

    def test_delete_manual_204(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("lancamentos", [_lancamento_row()])
        assert client.delete(f"/api/lancamentos/{LANCAMENTO_1}").status_code == 204

    def test_delete_automatico_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data(
            "lancamentos", [_lancamento_row(origem="estorno")],
        )
        resp = client.delete(f"/api/lancamentos/{LANCAMENTO_1}")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Lançamentos automáticos não podem ser alterados."

    def test_delete_404(self, client):
        seed_community_role(client, org_role="admin")
        assert client.delete(f"/api/lancamentos/{UNKNOWN_ID}").status_code == 404


class TestLancamentosList:
    def test_list_default_current_month_and_totais(self, client):
        client.mock_supabase.set_table_data("lancamentos", [
            _lancamento_row(id=LANCAMENTO_1, tipo="entrada", valor_centavos=2700, data="2026-06-10"),
            _lancamento_row(id=LANCAMENTO_2, tipo="saida", valor_centavos=1000, data="2026-06-11"),
            _lancamento_row(id="33333333-3333-3333-3333-333333333333",
                             tipo="entrada", valor_centavos=9999, data="2026-05-01"),
        ])
        with frozen_time(_NOW):
            resp = client.get("/api/lancamentos")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["totais"] == {
            "entradas_centavos": 2700, "saidas_centavos": 1000, "saldo_centavos": 1700,
        }

    def test_list_filters_by_tipo_and_categoria(self, client):
        client.mock_supabase.set_table_data("lancamentos", [
            _lancamento_row(id=LANCAMENTO_1, tipo="entrada", categoria="assinatura", data="2026-06-10"),
            _lancamento_row(id=LANCAMENTO_2, tipo="entrada", categoria="marketing", data="2026-06-11"),
        ])
        with frozen_time(_NOW):
            resp = client.get("/api/lancamentos", params={"categoria": "marketing"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == LANCAMENTO_2

    def test_list_denormalizes_membro_nome(self, client):
        client.mock_supabase.set_table_data("membros", [{
            "id": MEMBRO_1, "org_id": ORG_UUID, "nome": "Ana", "email": "ana@x.com",
            "telefone": None, "status": "ativo", "plano_id": None, "origem": "checkout",
            "tags": [], "user_id": None, "observacoes": None, "entrou_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        client.mock_supabase.set_table_data("lancamentos", [
            _lancamento_row(membro_id=MEMBRO_1, data="2026-06-10"),
        ])
        with frozen_time(_NOW):
            resp = client.get("/api/lancamentos")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["membro_nome"] == "Ana"


class TestLancamentosCategorias:
    def test_categorias_merges_used_and_defaults(self, client):
        client.mock_supabase.set_table_data("lancamentos", [
            _lancamento_row(id=LANCAMENTO_1, categoria="patrocinio"),
        ])
        resp = client.get("/api/lancamentos/categorias")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert "patrocinio" in items
        for default in ("assinatura", "estorno", "plataforma", "marketing", "equipe", "impostos", "outros"):
            assert default in items
