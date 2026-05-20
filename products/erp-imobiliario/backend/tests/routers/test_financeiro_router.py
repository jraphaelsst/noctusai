"""
Tests for the Financeiro CRUD router.
Covers list, create, read, update, delete, resumo, and fluxo de caixa.

erp-financial-surfaces-role-gate (2026-05-20): financeiro reads are now
role-gated to ("platform_admin", "owner", "admin", "manager"). The default
mock user has no `erp_role`, so an autouse fixture promotes it to "admin"
to preserve every existing test's contract (which tests business logic,
not the gate). The dedicated gate contract lives in
`test_financeiro_role_gate.py`.
"""
import pytest

from tests.conftest import MockSupabaseResponse


@pytest.fixture(autouse=True)
def _admin_default_role(client):
    """Promote default mock user to admin so non-gate tests stay green."""
    user = client._mock_supabase.auth.get_user.return_value.user
    user.user_metadata = {**(user.user_metadata or {}), "erp_role": "admin"}
    yield


class TestListarLancamentos:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "receita", "categoria": "Comissao",
             "descricao": "Venda apt 101", "valor": 15000,
             "data_vencimento": "2026-03-01", "status": "pendente"},
            {"id": "l2", "tipo": "despesa", "categoria": "Marketing",
             "descricao": "Anuncio portal", "valor": 500,
             "data_vencimento": "2026-02-15", "status": "pago"},
        ])
        resp = client.get("/api/financeiro")
        assert resp.status_code == 200

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "receita", "categoria": "Comissao",
             "descricao": "Venda", "valor": 15000,
             "data_vencimento": "2026-03-01", "status": "pago"},
        ])
        resp = client.get("/api/financeiro?tipo=receita")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "despesa", "categoria": "Aluguel",
             "descricao": "Escritorio", "valor": 3000,
             "data_vencimento": "2026-02-01", "status": "pago"},
        ])
        resp = client.get("/api/financeiro?status=pago")
        assert resp.status_code == 200

    def test_filter_by_categoria(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "receita", "categoria": "Comissao",
             "descricao": "Venda terreno", "valor": 8000,
             "data_vencimento": "2026-04-01", "status": "pendente"},
        ])
        resp = client.get("/api/financeiro?categoria=Comissao")
        assert resp.status_code == 200


class TestResumoFinanceiro:
    def test_resumo_success(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "receita", "valor": 15000, "status": "pago",
             "data_vencimento": "2026-01-15"},
            {"id": "l2", "tipo": "despesa", "valor": 3000, "status": "pago",
             "data_vencimento": "2026-01-20"},
            {"id": "l3", "tipo": "receita", "valor": 5000, "status": "atrasado",
             "data_vencimento": "2025-12-01"},
        ])
        resp = client.get("/api/financeiro/resumo")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "receitas" in data
        assert "despesas" in data
        assert "saldo" in data
        assert "atrasados" in data

    def test_resumo_empty(self, client):
        client._mock_supabase.set_table_data("lancamentos", [])
        resp = client.get("/api/financeiro/resumo")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["receitas"] == 0
        assert data["despesas"] == 0
        assert data["saldo"] == 0


class TestFluxoCaixa:
    def test_fluxo_success(self, client):
        client._mock_supabase.set_table_data("lancamentos", [
            {"id": "l1", "tipo": "receita", "valor": 10000, "status": "pago",
             "data_vencimento": "2026-01-15", "data_pagamento": "2026-01-15"},
            {"id": "l2", "tipo": "despesa", "valor": 2000, "status": "pago",
             "data_vencimento": "2026-01-20", "data_pagamento": "2026-01-20"},
            {"id": "l3", "tipo": "receita", "valor": 8000, "status": "pago",
             "data_vencimento": "2026-02-10", "data_pagamento": "2026-02-10"},
        ])
        resp = client.get("/api/financeiro/fluxo-caixa")
        assert resp.status_code == 200


class TestObterLancamento:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("lancamentos", {
            "id": "l1", "tipo": "receita", "categoria": "Comissao",
            "descricao": "Venda apt 101", "valor": 15000,
            "data_vencimento": "2026-03-01", "status": "pendente",
        })
        resp = client.get("/api/financeiro/l1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "l1"

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("lancamentos", None)
        resp = client.get("/api/financeiro/nonexistent")
        assert resp.status_code in [200, 404]


class TestCriarLancamento:
    def test_create_success(self, client):
        client._mock_supabase.set_sequential_responses("lancamentos", [
            MockSupabaseResponse(data=[{
                "id": "new-l", "tipo": "receita", "categoria": "Comissao",
                "descricao": "Comissao venda casa", "valor": 1000,
                "data_vencimento": "2026-03-01", "status": "pendente",
            }]),
        ])
        resp = client.post("/api/financeiro", json={
            "tipo": "receita",
            "categoria": "Comissao",
            "descricao": "Comissao venda casa",
            "valor": 1000,
            "data_vencimento": "2026-03-01",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "new-l"

    def test_create_missing_required(self, client):
        resp = client.post("/api/financeiro", json={
            "tipo": "receita",
            "categoria": "Comissao",
        })
        assert resp.status_code == 422


class TestAtualizarLancamento:
    def test_update_success(self, client):
        client._mock_supabase.set_table_data("lancamentos", {
            "id": "l1", "tipo": "receita", "categoria": "Comissao",
            "descricao": "Venda apt 101", "valor": 20000,
            "data_vencimento": "2026-03-01", "status": "pago",
        })
        resp = client.patch("/api/financeiro/l1", json={"status": "pago"})
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/financeiro/l1", json={})
        assert resp.status_code == 400


class TestExcluirLancamento:
    def test_delete_success(self, client):
        client._mock_supabase.set_table_data("lancamentos", {
            "id": "l1", "tipo": "receita", "categoria": "Comissao",
            "descricao": "Venda apt 101", "valor": 15000,
            "data_vencimento": "2026-03-01", "status": "pago",
        })
        resp = client.delete("/api/financeiro/l1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_not_found(self, client):
        resp = client.delete("/api/financeiro/nonexistent")
        assert resp.status_code == 404


class TestNoAuth:
    def test_no_token(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/financeiro")
        assert resp.status_code == 401
