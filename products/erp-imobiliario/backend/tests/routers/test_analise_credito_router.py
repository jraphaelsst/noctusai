"""
Tests for the Analise de Credito (Credit Analysis) router — /api/analise-credito
Covers credit consultation, single read, update, and listing.
"""
import pytest
from unittest.mock import patch

from tests.conftest import MockSupabaseResponse


class TestConsultarCredito:
    def test_consulta_manual_success(self, client):
        client._mock_supabase.set_sequential_responses("analises_credito", [
            MockSupabaseResponse(data=[{
                "id": "ac-new", "cpf": "12345678901", "nome": "Joao Silva",
                "fonte": "manual", "status": "aprovado", "score": 750,
            }]),
        ])
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "nome": "Joao Silva",
            "fonte": "manual",
            "score": 750,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "ac-new"

    def test_consulta_manual_low_score(self, client):
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-low", "cpf": "12345678901", "nome": "Maria Santos",
            "fonte": "manual", "status": "reprovado", "score": 200,
        })
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "nome": "Maria Santos",
            "fonte": "manual",
            "score": 200,
        })
        assert resp.status_code == 200

    def test_consulta_manual_medium_score(self, client):
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-med", "cpf": "12345678901", "nome": "Pedro Costa",
            "fonte": "manual", "status": "em_analise", "score": 500,
        })
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "nome": "Pedro Costa",
            "fonte": "manual",
            "score": 500,
        })
        assert resp.status_code == 200

    def test_consulta_serasa(self, client):
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-serasa", "cpf": "12345678901", "nome": "Ana Lima",
            "fonte": "serasa", "status": "pendente",
        })
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "nome": "Ana Lima",
            "fonte": "serasa",
        })
        assert resp.status_code == 200

    def test_consulta_boa_vista(self, client):
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-bv", "cpf": "12345678901", "nome": "Carlos Souza",
            "fonte": "boa_vista", "status": "pendente",
        })
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "nome": "Carlos Souza",
            "fonte": "boa_vista",
        })
        assert resp.status_code == 200

    def test_consulta_with_cliente_id(self, client):
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-cl", "cpf": "12345678901", "nome": "Joao Silva",
            "fonte": "manual", "cliente_id": "cl-1",
        })
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "nome": "Joao Silva",
            "fonte": "manual",
            "cliente_id": "cl-1",
        })
        assert resp.status_code == 200

    def test_consulta_cpf_formatted(self, client):
        """CPF with dots and dash should be accepted and cleaned."""
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-fmt", "cpf": "12345678901", "nome": "Test",
            "fonte": "manual", "status": "pendente",
        })
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "123.456.789-01",
            "nome": "Test",
            "fonte": "manual",
        })
        assert resp.status_code == 200

    def test_consulta_missing_cpf(self, client):
        resp = client.post("/api/analise-credito/consultar", json={
            "nome": "Test",
            "fonte": "manual",
        })
        assert resp.status_code == 422

    def test_consulta_missing_nome(self, client):
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "fonte": "manual",
        })
        assert resp.status_code == 422

    def test_consulta_cpf_too_short(self, client):
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345",
            "nome": "Test",
            "fonte": "manual",
        })
        assert resp.status_code == 422

    def test_consulta_invalid_fonte(self, client):
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "nome": "Test",
            "fonte": "spc",
        })
        assert resp.status_code == 422

    def test_consulta_score_out_of_range(self, client):
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "nome": "Test",
            "fonte": "manual",
            "score": 1500,
        })
        assert resp.status_code == 422

    def test_consulta_score_negative(self, client):
        resp = client.post("/api/analise-credito/consultar", json={
            "cpf": "12345678901",
            "nome": "Test",
            "fonte": "manual",
            "score": -10,
        })
        assert resp.status_code == 422


class TestObterAnalise:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-1", "cpf": "12345678901", "nome": "Joao",
            "status": "aprovado", "score": 800,
        })
        resp = client.get("/api/analise-credito/ac-1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "ac-1"

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("analises_credito", None)
        resp = client.get("/api/analise-credito/nonexistent")
        assert resp.status_code == 404


class TestAtualizarAnalise:
    def test_update_status(self, client):
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-1", "cpf": "12345678901", "nome": "Joao",
            "status": "aprovado", "score": 800,
        })
        resp = client.patch("/api/analise-credito/ac-1", json={
            "status": "aprovado",
        })
        assert resp.status_code == 200

    def test_update_score(self, client):
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-1", "cpf": "12345678901", "nome": "Joao",
            "status": "em_analise", "score": 650,
        })
        resp = client.patch("/api/analise-credito/ac-1", json={
            "score": 650,
        })
        assert resp.status_code == 200

    def test_update_validade(self, client):
        client._mock_supabase.set_table_data("analises_credito", {
            "id": "ac-1", "cpf": "12345678901", "nome": "Joao",
            "validade": "2026-06-01",
        })
        resp = client.patch("/api/analise-credito/ac-1", json={
            "validade": "2026-06-01",
        })
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/analise-credito/ac-1", json={})
        assert resp.status_code == 400

    def test_update_not_found(self, client):
        client._mock_supabase.set_table_data("analises_credito", None)
        resp = client.patch("/api/analise-credito/nonexistent", json={
            "status": "reprovado",
        })
        assert resp.status_code == 404

    def test_update_invalid_status(self, client):
        resp = client.patch("/api/analise-credito/ac-1", json={
            "status": "invalido",
        })
        assert resp.status_code == 422

    def test_update_score_out_of_range(self, client):
        resp = client.patch("/api/analise-credito/ac-1", json={
            "score": 2000,
        })
        assert resp.status_code == 422


class TestListarAnalises:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("analises_credito", [
            {"id": "ac-1", "cpf": "12345678901", "nome": "Joao", "status": "aprovado"},
            {"id": "ac-2", "cpf": "98765432100", "nome": "Maria", "status": "pendente"},
        ])
        resp = client.get("/api/analise-credito")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("analises_credito", [])
        resp = client.get("/api/analise-credito?status=aprovado")
        assert resp.status_code == 200

    def test_filter_by_fonte(self, client):
        client._mock_supabase.set_table_data("analises_credito", [])
        resp = client.get("/api/analise-credito?fonte=manual")
        assert resp.status_code == 200

    def test_filter_by_cpf(self, client):
        client._mock_supabase.set_table_data("analises_credito", [])
        resp = client.get("/api/analise-credito?cpf=12345678901")
        assert resp.status_code == 200

    def test_filter_by_cliente_id(self, client):
        client._mock_supabase.set_table_data("analises_credito", [])
        resp = client.get("/api/analise-credito?cliente_id=cl-1")
        assert resp.status_code == 200

    def test_pagination(self, client):
        client._mock_supabase.set_table_data("analises_credito", [])
        resp = client.get("/api/analise-credito?page=2&page_size=10")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page"] == 2


class TestNoAuth:
    def test_no_token(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/analise-credito")
        assert resp.status_code == 401
