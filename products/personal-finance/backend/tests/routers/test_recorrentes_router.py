"""Tests for recorrentes (recurring transactions) router."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, AsyncMock

yesterday = (date.today() - timedelta(days=1)).isoformat()
tomorrow = (date.today() + timedelta(days=1)).isoformat()
in_three_days = (date.today() + timedelta(days=3)).isoformat()

SAMPLE_RECORRENTE = {
    "id": "rec-001",
    "org_id": "test-org-123",
    "nome": "Aluguel",
    "valor": 2500.00,
    "conta_id": "conta-001",
    "categoria_id": "cat-001",
    "tipo": "despesa",
    "frequencia": "mensal",
    "dia_vencimento": 5,
    "proxima_data": in_three_days,
    "is_automatico": True,
    "comerciante": "Imobiliaria XYZ",
    "lembrete_dias": 3,
    "ativo": True,
    "created_at": "2026-01-01T10:00:00",
    "conta": {"id": "conta-001", "nome": "Conta Corrente"},
    "categoria": {"id": "cat-001", "nome": "Moradia", "icone": "home", "cor": "#ef4444"},
}

SAMPLE_RECORRENTE_2 = {
    "id": "rec-002",
    "org_id": "test-org-123",
    "nome": "Salario",
    "valor": 8000.00,
    "conta_id": "conta-001",
    "categoria_id": "cat-002",
    "tipo": "receita",
    "frequencia": "mensal",
    "dia_vencimento": 1,
    "proxima_data": tomorrow,
    "is_automatico": False,
    "comerciante": None,
    "lembrete_dias": 0,
    "ativo": True,
    "created_at": "2026-01-01T10:00:00",
    "conta": {"id": "conta-001", "nome": "Conta Corrente"},
    "categoria": {"id": "cat-002", "nome": "Salario", "icone": "briefcase", "cor": "#22c55e"},
}


class TestListarRecorrentes:
    def test_returns_list(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE, SAMPLE_RECORRENTE_2])
        response = client.get("/api/recorrentes")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_returns_total(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        response = client.get("/api/recorrentes")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    def test_filter_by_ativo(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        response = client.get("/api/recorrentes?ativo=true")
        assert response.status_code == 200

    def test_filter_by_ativo_false(self, client):
        client._mock_supabase.set_table_data("recorrentes", [])
        response = client.get("/api/recorrentes?ativo=false")
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.get("/api/recorrentes")
        assert response.status_code == 401


class TestProximasContas:
    def test_returns_upcoming(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        response = client.get("/api/recorrentes/proximas")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_custom_dias_param(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        response = client.get("/api/recorrentes/proximas?dias=30")
        assert response.status_code == 200

    def test_dias_validation_min(self, client):
        response = client.get("/api/recorrentes/proximas?dias=0")
        assert response.status_code == 422

    def test_dias_validation_max(self, client):
        response = client.get("/api/recorrentes/proximas?dias=91")
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.get("/api/recorrentes/proximas")
        assert response.status_code == 401


class TestObterRecorrente:
    def test_returns_single(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        response = client.get("/api/recorrentes/rec-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/recorrentes/rec-001")
        assert response.status_code == 401


class TestCriarRecorrente:
    def test_creates_recorrente(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        response = client.post("/api/recorrentes", json={
            "nome": "Aluguel",
            "valor": 2500.00,
            "tipo": "despesa",
            "frequencia": "mensal",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_nome(self, client):
        response = client.post("/api/recorrentes", json={
            "valor": 2500.00,
            "tipo": "despesa",
            "frequencia": "mensal",
        })
        assert response.status_code == 422

    def test_requires_valor(self, client):
        response = client.post("/api/recorrentes", json={
            "nome": "Aluguel",
            "tipo": "despesa",
            "frequencia": "mensal",
        })
        assert response.status_code == 422

    def test_validates_tipo(self, client):
        response = client.post("/api/recorrentes", json={
            "nome": "Aluguel",
            "valor": 2500.00,
            "tipo": "invalido",
            "frequencia": "mensal",
        })
        assert response.status_code == 422

    def test_validates_frequencia(self, client):
        response = client.post("/api/recorrentes", json={
            "nome": "Aluguel",
            "valor": 2500.00,
            "tipo": "despesa",
            "frequencia": "invalida",
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/recorrentes", json={
            "nome": "Aluguel",
            "valor": 2500.00,
            "tipo": "despesa",
            "frequencia": "mensal",
        })
        assert response.status_code == 401


class TestAtualizarRecorrente:
    def test_updates_recorrente(self, client):
        updated = {**SAMPLE_RECORRENTE, "valor": 3000.00}
        client._mock_supabase.set_table_data("recorrentes", [updated])
        response = client.patch("/api/recorrentes/rec-001", json={"valor": 3000.00})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_empty_update_returns_400(self, client):
        response = client.patch("/api/recorrentes/rec-001", json={})
        assert response.status_code == 400

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/recorrentes/rec-001", json={"valor": 3000.00})
        assert response.status_code == 401


class TestExcluirRecorrente:
    def test_deletes_recorrente(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        response = client.delete("/api/recorrentes/rec-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/recorrentes/rec-001")
        assert response.status_code == 401


class TestExecutarPendentes:
    def test_executes_pending(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        client._mock_supabase.set_table_data("transacoes", [{"id": "tx-001"}])
        client._mock_supabase.set_table_data("contas", [{"id": "conta-001", "saldo": 10000.00}])
        response = client.post("/api/recorrentes/executar")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.post("/api/recorrentes/executar")
        assert response.status_code == 401


class TestExecutarUnico:
    def test_executes_single(self, client):
        client._mock_supabase.set_table_data("recorrentes", [SAMPLE_RECORRENTE])
        client._mock_supabase.set_table_data("transacoes", [{"id": "tx-001"}])
        client._mock_supabase.set_table_data("contas", [{"id": "conta-001", "saldo": 10000.00}])
        response = client.post("/api/recorrentes/rec-001/executar")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.post("/api/recorrentes/rec-001/executar")
        assert response.status_code == 401
