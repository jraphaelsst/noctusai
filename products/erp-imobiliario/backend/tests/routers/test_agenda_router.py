"""
Tests for the Agenda (Calendar) router — /api/agenda
Covers event CRUD, today/week views, and conflict detection.
"""
import pytest
from unittest.mock import patch
from tests.conftest import MockSupabaseResponse


class TestListarEventos:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("eventos", [
            {"id": "e1", "titulo": "Visita Apto 101", "tipo": "visita", "status": "agendado"},
            {"id": "e2", "titulo": "Reuniao Escritorio", "tipo": "reuniao", "status": "confirmado"},
        ])
        resp = client.get("/api/agenda")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("eventos", [
            {"id": "e1", "titulo": "Visita", "tipo": "visita", "status": "agendado"},
        ])
        resp = client.get("/api/agenda?tipo=visita")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("eventos", [])
        resp = client.get("/api/agenda?status=cancelado")
        assert resp.status_code == 200

    def test_filter_by_corretor_id(self, client):
        client._mock_supabase.set_table_data("eventos", [])
        resp = client.get("/api/agenda?corretor_id=user-abc")
        assert resp.status_code == 200

    def test_filter_by_date_range(self, client):
        client._mock_supabase.set_table_data("eventos", [])
        resp = client.get(
            "/api/agenda?data_inicio=2026-02-20T00:00:00&data_fim=2026-02-28T23:59:59"
        )
        assert resp.status_code == 200

    def test_pagination(self, client):
        client._mock_supabase.set_table_data("eventos", [])
        resp = client.get("/api/agenda?page=2&page_size=25")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page"] == 2


class TestCriarEvento:
    @staticmethod
    def _setup_sequential(client, table, responses):
        """Set up sequential execute() responses via the response queue."""
        client._mock_supabase.set_sequential_responses(table, responses)

    def test_create_success(self, client):
        self._setup_sequential(client, "eventos", [
            MockSupabaseResponse(data=[]),  # conflict check: no conflict
            MockSupabaseResponse(data={"id": "e-new", "titulo": "Visita Imovel",
                "tipo": "visita", "status": "agendado",
                "data_inicio": "2026-03-01T10:00:00", "data_fim": "2026-03-01T11:00:00"}),
        ])
        resp = client.post("/api/agenda", json={
            "titulo": "Visita Imovel",
            "tipo": "visita",
            "data_inicio": "2026-03-01T10:00:00",
            "data_fim": "2026-03-01T11:00:00",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "e-new"

    def test_create_with_all_fields(self, client):
        self._setup_sequential(client, "eventos", [
            MockSupabaseResponse(data=[]),  # conflict check: no conflict
            MockSupabaseResponse(data={"id": "e-full", "titulo": "Assinatura Contrato",
                "tipo": "assinatura", "status": "confirmado"}),
        ])
        resp = client.post("/api/agenda", json={
            "titulo": "Assinatura Contrato",
            "tipo": "assinatura",
            "data_inicio": "2026-03-05T14:00:00",
            "data_fim": "2026-03-05T15:00:00",
            "local": "Cartorio Central",
            "cliente_id": "cl-1",
            "imovel_id": "im-1",
            "status": "confirmado",
            "cor": "#22c55e",
            "descricao": "Assinatura do contrato de compra e venda",
        })
        assert resp.status_code == 200

    def test_create_missing_titulo(self, client):
        resp = client.post("/api/agenda", json={
            "tipo": "visita",
            "data_inicio": "2026-03-01T10:00:00",
            "data_fim": "2026-03-01T11:00:00",
        })
        assert resp.status_code == 422

    def test_create_missing_tipo(self, client):
        resp = client.post("/api/agenda", json={
            "titulo": "Test",
            "data_inicio": "2026-03-01T10:00:00",
            "data_fim": "2026-03-01T11:00:00",
        })
        assert resp.status_code == 422

    def test_create_invalid_tipo(self, client):
        resp = client.post("/api/agenda", json={
            "titulo": "Test",
            "tipo": "invalido",
            "data_inicio": "2026-03-01T10:00:00",
            "data_fim": "2026-03-01T11:00:00",
        })
        assert resp.status_code == 422

    def test_create_missing_data_inicio(self, client):
        resp = client.post("/api/agenda", json={
            "titulo": "Test",
            "tipo": "visita",
            "data_fim": "2026-03-01T11:00:00",
        })
        assert resp.status_code == 422


class TestEventosHoje:
    def test_hoje_success(self, client):
        client._mock_supabase.set_table_data("eventos", [
            {"id": "e1", "titulo": "Visita Manha", "tipo": "visita"},
        ])
        resp = client.get("/api/agenda/hoje")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_hoje_empty(self, client):
        client._mock_supabase.set_table_data("eventos", [])
        resp = client.get("/api/agenda/hoje")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestEventosSemana:
    def test_semana_success(self, client):
        client._mock_supabase.set_table_data("eventos", [
            {"id": "e1", "titulo": "Reuniao Seg", "tipo": "reuniao"},
            {"id": "e2", "titulo": "Visita Ter", "tipo": "visita"},
        ])
        resp = client.get("/api/agenda/semana")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_semana_empty(self, client):
        client._mock_supabase.set_table_data("eventos", [])
        resp = client.get("/api/agenda/semana")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestObterEvento:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("eventos", {
            "id": "e1", "titulo": "Visita Apto 202", "tipo": "visita", "status": "agendado",
        })
        resp = client.get("/api/agenda/e1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "e1"

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("eventos", None)
        resp = client.get("/api/agenda/nonexistent")
        assert resp.status_code == 404


class TestAtualizarEvento:
    def test_update_titulo(self, client):
        client._mock_supabase.set_table_data("eventos", {
            "id": "e1", "titulo": "Atualizado", "tipo": "visita", "status": "agendado",
        })
        resp = client.patch("/api/agenda/e1", json={"titulo": "Atualizado"})
        assert resp.status_code == 200

    def test_update_status(self, client):
        client._mock_supabase.set_table_data("eventos", {
            "id": "e1", "titulo": "Test", "tipo": "visita", "status": "cancelado",
        })
        resp = client.patch("/api/agenda/e1", json={"status": "cancelado"})
        assert resp.status_code == 200

    def test_update_date_range(self, client):
        event_data = {
            "id": "e1", "titulo": "Test", "tipo": "visita",
            "data_inicio": "2026-03-02T10:00:00", "data_fim": "2026-03-02T11:00:00",
            "corretor_id": "test-user-123",
        }
        TestCriarEvento._setup_sequential(client, "eventos", [
            MockSupabaseResponse(data=event_data),   # fetch existing event
            MockSupabaseResponse(data=[]),            # conflict check: no conflict
            MockSupabaseResponse(data=event_data),    # update result
        ])
        resp = client.patch("/api/agenda/e1", json={
            "data_inicio": "2026-03-02T10:00:00",
            "data_fim": "2026-03-02T11:00:00",
        })
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/agenda/e1", json={})
        assert resp.status_code == 400

    def test_update_not_found(self, client):
        client._mock_supabase.set_table_data("eventos", None)
        resp = client.patch("/api/agenda/nonexistent", json={"titulo": "X"})
        assert resp.status_code == 404

    def test_update_invalid_status(self, client):
        resp = client.patch("/api/agenda/e1", json={"status": "invalido"})
        assert resp.status_code == 422


class TestExcluirEvento:
    def test_delete_success(self, client):
        client._mock_supabase.set_table_data("eventos", [{"id": "e1"}])
        resp = client.delete("/api/agenda/e1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_message(self, client):
        client._mock_supabase.set_table_data("eventos", [{"id": "e1"}])
        resp = client.delete("/api/agenda/e1")
        assert resp.status_code == 200
        assert "sucesso" in resp.json()["message"].lower()

    def test_delete_not_found(self, client):
        client._mock_supabase.set_table_data("eventos", [])
        resp = client.delete("/api/agenda/nonexistent")
        assert resp.status_code == 404


class TestNoAuth:
    def test_no_token(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/agenda")
        assert resp.status_code == 401
