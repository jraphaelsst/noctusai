"""Tests for contas (accounts) router."""
import pytest


SAMPLE_CONTA = {
    "id": "conta-001",
    "org_id": "test-org-123",
    "nome": "Conta Corrente",
    "tipo": "corrente",
    "instituicao": "Banco do Brasil",
    "saldo": 5000.00,
    "moeda": "BRL",
    "cor": "#6366f1",
    "icone": None,
    "ativo": True,
    "created_at": "2026-01-15T10:00:00",
}

SAMPLE_CONTA_2 = {
    "id": "conta-002",
    "org_id": "test-org-123",
    "nome": "Poupanca",
    "tipo": "poupanca",
    "instituicao": "Nubank",
    "saldo": 12000.50,
    "moeda": "BRL",
    "cor": "#22c55e",
    "icone": None,
    "ativo": True,
    "created_at": "2026-01-20T10:00:00",
}


class TestListarContas:
    def test_returns_accounts_list(self, client):
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA, SAMPLE_CONTA_2])
        response = client.get("/api/contas")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_returns_total_count(self, client):
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA])
        response = client.get("/api/contas")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    def test_filter_by_ativo(self, client):
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA])
        response = client.get("/api/contas?ativo=true")
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.get("/api/contas")
        assert response.status_code == 401


class TestObterConta:
    def test_returns_single_account(self, client):
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA])
        response = client.get("/api/contas/conta-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/contas/conta-001")
        assert response.status_code == 401


class TestObterSaldos:
    def test_returns_balances(self, client):
        client._mock_supabase.set_table_data("contas", [
            {"id": "conta-001", "nome": "Corrente", "tipo": "corrente", "saldo": 5000.00, "ativo": True},
            {"id": "conta-002", "nome": "Poupanca", "tipo": "poupanca", "saldo": 12000.00, "ativo": True},
        ])
        response = client.get("/api/contas/saldos")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/contas/saldos")
        assert response.status_code == 401


class TestCriarConta:
    def test_creates_account(self, client):
        client._mock_supabase.set_table_data("contas", [SAMPLE_CONTA])
        response = client.post("/api/contas", json={
            "nome": "Conta Corrente",
            "tipo": "corrente",
            "instituicao": "Banco do Brasil",
            "saldo": 5000.00,
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_nome(self, client):
        response = client.post("/api/contas", json={
            "tipo": "corrente",
        })
        assert response.status_code == 422

    def test_validates_tipo(self, client):
        response = client.post("/api/contas", json={
            "nome": "Conta",
            "tipo": "invalido",
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/contas", json={
            "nome": "Conta Corrente",
            "tipo": "corrente",
        })
        assert response.status_code == 401


class TestAtualizarConta:
    def test_updates_account(self, client):
        updated = {**SAMPLE_CONTA, "nome": "Conta Atualizada"}
        client._mock_supabase.set_table_data("contas", [updated])
        response = client.patch("/api/contas/conta-001", json={"nome": "Conta Atualizada"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_empty_update_returns_400(self, client):
        response = client.patch("/api/contas/conta-001", json={})
        assert response.status_code == 400

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/contas/conta-001", json={"nome": "Teste"})
        assert response.status_code == 401


class TestExcluirConta:
    def test_deletes_account(self, client):
        client._mock_supabase.set_table_data("contas", [{"id": "conta-001", "org_id": "test-org-123"}])
        response = client.delete("/api/contas/conta-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "excluida" in data["message"]

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/contas/conta-001")
        assert response.status_code == 401


class TestHealth:
    def test_health_check(self, client):
        response = client._tc.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["product"] == "personal-finance"
