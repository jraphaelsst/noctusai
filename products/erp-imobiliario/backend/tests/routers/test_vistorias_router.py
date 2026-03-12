"""
Tests for Vistorias (property inspections) router — /api/vistorias
"""
import pytest
from unittest.mock import patch


class TestListarVistorias:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("vistorias", [
            {"id": "v1", "imovel_id": "im1", "tipo": "entrada", "status": "agendada"},
            {"id": "v2", "imovel_id": "im2", "tipo": "saida", "status": "concluida"},
        ])
        resp = client.get("/api/vistorias")
        assert resp.status_code == 200

    def test_filter_by_imovel(self, client):
        client._mock_supabase.set_table_data("vistorias", [
            {"id": "v1", "imovel_id": "im1", "tipo": "entrada", "status": "agendada"},
        ])
        resp = client.get("/api/vistorias?imovel_id=im1")
        assert resp.status_code == 200

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("vistorias", [
            {"id": "v1", "tipo": "periodica", "status": "agendada"},
        ])
        resp = client.get("/api/vistorias?tipo=periodica")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("vistorias", [
            {"id": "v1", "tipo": "entrada", "status": "concluida"},
        ])
        resp = client.get("/api/vistorias?status=concluida")
        assert resp.status_code == 200

    def test_filter_combined(self, client):
        client._mock_supabase.set_table_data("vistorias", [
            {"id": "v1", "imovel_id": "im1", "tipo": "entrada", "status": "agendada"},
        ])
        resp = client.get("/api/vistorias?imovel_id=im1&tipo=entrada&status=agendada")
        assert resp.status_code == 200

    def test_list_with_pagination(self, client):
        client._mock_supabase.set_table_data("vistorias", [
            {"id": "v1", "tipo": "entrada", "status": "agendada"},
        ])
        resp = client.get("/api/vistorias?page=1&page_size=10")
        assert resp.status_code == 200


class TestCriarVistoria:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("vistorias", {
            "id": "v-new",
            "imovel_id": "im1",
            "tipo": "entrada",
            "data_vistoria": "2026-03-15",
            "responsavel_id": "user1",
            "status": "agendada",
            "checklist": [],
            "fotos": [],
        })
        resp = client.post("/api/vistorias", json={
            "imovel_id": "im1",
            "tipo": "entrada",
            "data_vistoria": "2026-03-15",
            "responsavel_id": "user1",
        })
        assert resp.status_code == 200

    def test_create_with_checklist(self, client):
        client._mock_supabase.set_table_data("vistorias", {
            "id": "v-ck",
            "imovel_id": "im1",
            "tipo": "saida",
            "data_vistoria": "2026-03-20",
            "responsavel_id": "user1",
            "status": "agendada",
            "checklist": [
                {"item": "Paredes", "estado": "bom", "observacao": ""},
                {"item": "Piso", "estado": "regular", "observacao": "Riscos leves"},
            ],
        })
        resp = client.post("/api/vistorias", json={
            "imovel_id": "im1",
            "tipo": "saida",
            "data_vistoria": "2026-03-20",
            "responsavel_id": "user1",
            "checklist": [
                {"item": "Paredes", "estado": "bom"},
                {"item": "Piso", "estado": "regular", "observacao": "Riscos leves"},
            ],
        })
        assert resp.status_code == 200

    def test_create_with_fotos(self, client):
        client._mock_supabase.set_table_data("vistorias", {
            "id": "v-ft",
            "imovel_id": "im1",
            "tipo": "periodica",
            "data_vistoria": "2026-04-01",
            "responsavel_id": "user1",
            "fotos": ["https://storage.example.com/foto1.jpg"],
        })
        resp = client.post("/api/vistorias", json={
            "imovel_id": "im1",
            "tipo": "periodica",
            "data_vistoria": "2026-04-01",
            "responsavel_id": "user1",
            "fotos": ["https://storage.example.com/foto1.jpg"],
        })
        assert resp.status_code == 200

    def test_create_missing_required(self, client):
        resp = client.post("/api/vistorias", json={})
        assert resp.status_code == 422

    def test_create_invalid_tipo(self, client):
        resp = client.post("/api/vistorias", json={
            "imovel_id": "im1",
            "tipo": "invalido",
            "data_vistoria": "2026-03-15",
            "responsavel_id": "user1",
        })
        assert resp.status_code == 422


class TestObterTemplateChecklist:
    def test_get_template(self, client):
        resp = client.get("/api/vistorias/template-checklist")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) > 0
        assert "item" in data[0]
        assert "estado" in data[0]


class TestObterVistoria:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("vistorias", {
            "id": "v1",
            "imovel_id": "im1",
            "tipo": "entrada",
            "data_vistoria": "2026-03-15",
            "responsavel_id": "user1",
            "status": "concluida",
            "checklist": [
                {"item": "Paredes", "estado": "bom", "observacao": ""},
                {"item": "Piso", "estado": "ruim", "observacao": "Danificado"},
            ],
            "fotos": [],
        })
        resp = client.get("/api/vistorias/v1")
        assert resp.status_code == 200

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("vistorias", None)
        resp = client.get("/api/vistorias/nonexistent")
        assert resp.status_code == 404


class TestAtualizarVistoria:
    def test_update_status(self, client):
        client._mock_supabase.set_table_data("vistorias", {
            "id": "v1", "status": "em_andamento",
        })
        resp = client.patch("/api/vistorias/v1", json={
            "status": "em_andamento",
        })
        assert resp.status_code == 200

    def test_update_checklist(self, client):
        client._mock_supabase.set_table_data("vistorias", {
            "id": "v1",
            "checklist": [
                {"item": "Paredes", "estado": "regular", "observacao": "Manchas"},
            ],
        })
        resp = client.patch("/api/vistorias/v1", json={
            "checklist": [
                {"item": "Paredes", "estado": "regular", "observacao": "Manchas"},
            ],
        })
        assert resp.status_code == 200

    def test_update_observacoes(self, client):
        client._mock_supabase.set_table_data("vistorias", {
            "id": "v1", "observacoes_gerais": "Imovel em bom estado geral",
        })
        resp = client.patch("/api/vistorias/v1", json={
            "observacoes_gerais": "Imovel em bom estado geral",
        })
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/vistorias/v1", json={})
        assert resp.status_code == 400

    def test_update_not_found(self, client):
        client._mock_supabase.set_table_data("vistorias", None)
        resp = client.patch("/api/vistorias/v1", json={
            "status": "concluida",
        })
        assert resp.status_code == 404


class TestExcluirVistoria:
    def test_delete(self, client):
        client._mock_supabase.set_table_data("vistorias", [{"id": "v1"}])
        resp = client.delete("/api/vistorias/v1")
        assert resp.status_code == 200

    def test_delete_not_found(self, client):
        client._mock_supabase.set_table_data("vistorias", [])
        resp = client.delete("/api/vistorias/nonexistent")
        assert resp.status_code == 404


class TestAdicionarFotos:
    def test_add_fotos_success(self, client):
        client._mock_supabase.set_table_data("vistorias", {
            "id": "v1",
            "fotos": [
                "https://storage.example.com/foto1.jpg",
                "https://storage.example.com/foto2.jpg",
                "https://storage.example.com/foto3.jpg",
            ],
        })
        resp = client.post("/api/vistorias/v1/fotos", json={
            "urls": [
                "https://storage.example.com/foto2.jpg",
                "https://storage.example.com/foto3.jpg",
            ],
        })
        assert resp.status_code == 200

    def test_add_fotos_not_found(self, client):
        client._mock_supabase.set_table_data("vistorias", None)
        resp = client.post("/api/vistorias/nonexistent/fotos", json={
            "urls": ["https://storage.example.com/foto1.jpg"],
        })
        assert resp.status_code == 404

    def test_add_fotos_empty_urls(self, client):
        resp = client.post("/api/vistorias/v1/fotos", json={
            "urls": [],
        })
        assert resp.status_code == 422

    def test_add_fotos_missing_urls(self, client):
        resp = client.post("/api/vistorias/v1/fotos", json={})
        assert resp.status_code == 422
