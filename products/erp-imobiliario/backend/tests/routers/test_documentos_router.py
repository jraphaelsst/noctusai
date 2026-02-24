"""
Tests for Documentos CRUD router — /api/documentos
Covers list, get by id, create, delete, templates, and generate.
"""
import pytest


class TestListarDocumentos:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("documentos", [
            {"id": "d1", "nome": "Contrato Venda", "tipo": "contrato",
             "created_at": "2026-01-10T10:00:00Z"},
            {"id": "d2", "nome": "Procuração", "tipo": "procuracao",
             "created_at": "2026-01-12T10:00:00Z"},
        ])
        resp = client.get("/api/documentos")
        assert resp.status_code == 200

    def test_list_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("documentos", [
            {"id": "d1", "nome": "Contrato A", "tipo": "contrato"},
        ])
        resp = client.get("/api/documentos?tipo=contrato")
        assert resp.status_code == 200

    def test_list_filter_by_imovel_id(self, client):
        client._mock_supabase.set_table_data("documentos", [
            {"id": "d1", "nome": "Laudo", "tipo": "laudo", "imovel_id": "imv-1"},
        ])
        resp = client.get("/api/documentos?imovel_id=imv-1")
        assert resp.status_code == 200

    def test_list_filter_by_cliente_id(self, client):
        client._mock_supabase.set_table_data("documentos", [])
        resp = client.get("/api/documentos?cliente_id=cli-1")
        assert resp.status_code == 200

    def test_list_filter_by_proposta_id(self, client):
        client._mock_supabase.set_table_data("documentos", [])
        resp = client.get("/api/documentos?proposta_id=prop-1")
        assert resp.status_code == 200


class TestObterDocumento:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("documentos", {
            "id": "d1", "nome": "Contrato Venda", "tipo": "contrato",
            "arquivo_url": "https://storage.example.com/doc.pdf",
        })
        resp = client.get("/api/documentos/d1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "d1"

    def test_get_not_found(self, client):
        client._mock_supabase.set_table_data("documentos", None)
        resp = client.get("/api/documentos/nonexistent")
        assert resp.status_code == 404


class TestCriarDocumento:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("documentos", {
            "id": "d-new", "nome": "Novo Contrato", "tipo": "contrato",
        })
        resp = client.post("/api/documentos", json={
            "nome": "Novo Contrato",
            "tipo": "contrato",
        })
        assert resp.status_code == 200

    def test_create_with_all_fields(self, client):
        client._mock_supabase.set_table_data("documentos", {
            "id": "d-full", "nome": "Full Doc", "tipo": "laudo",
        })
        resp = client.post("/api/documentos", json={
            "nome": "Full Doc",
            "tipo": "laudo",
            "arquivo_url": "https://storage.example.com/laudo.pdf",
            "arquivo_path": "/docs/laudo.pdf",
            "tamanho_bytes": 1024,
            "mime_type": "application/pdf",
            "imovel_id": "imv-1",
            "cliente_id": "cli-1",
            "proposta_id": "prop-1",
            "metadata": {"origin": "upload"},
        })
        assert resp.status_code == 200

    def test_create_missing_nome(self, client):
        resp = client.post("/api/documentos", json={
            "tipo": "contrato",
        })
        assert resp.status_code == 422

    def test_create_missing_tipo(self, client):
        resp = client.post("/api/documentos", json={
            "nome": "Sem Tipo",
        })
        assert resp.status_code == 422

    def test_create_invalid_tipo(self, client):
        resp = client.post("/api/documentos", json={
            "nome": "Bad Type",
            "tipo": "invalido",
        })
        assert resp.status_code == 422


class TestExcluirDocumento:
    def test_delete(self, client):
        resp = client.delete("/api/documentos/d1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True


class TestListarTemplates:
    def test_list_templates(self, client):
        client._mock_supabase.set_table_data("document_templates", [
            {"id": "t1", "nome": "Template Contrato", "tipo": "contrato",
             "conteudo": "Contrato de {{nome}}", "is_active": True},
        ])
        resp = client.get("/api/documentos/templates")
        assert resp.status_code == 200

    def test_list_templates_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("document_templates", [])
        resp = client.get("/api/documentos/templates?tipo=procuracao")
        assert resp.status_code == 200


class TestCriarTemplate:
    def test_create_template_success(self, client):
        client._mock_supabase.set_table_data("document_templates", {
            "id": "t-new", "nome": "Template Novo", "tipo": "contrato",
            "conteudo": "Contrato de {{nome}} para {{imovel}}",
            "variaveis": ["nome", "imovel"],
        })
        resp = client.post("/api/documentos/templates", json={
            "nome": "Template Novo",
            "tipo": "contrato",
            "conteudo": "Contrato de {{nome}} para {{imovel}}",
            "variaveis": ["nome", "imovel"],
        })
        assert resp.status_code == 200

    def test_create_template_missing_nome(self, client):
        resp = client.post("/api/documentos/templates", json={
            "tipo": "contrato",
            "conteudo": "Conteudo",
        })
        assert resp.status_code == 422

    def test_create_template_missing_conteudo(self, client):
        resp = client.post("/api/documentos/templates", json={
            "nome": "Template",
            "tipo": "contrato",
        })
        assert resp.status_code == 422

    def test_create_template_invalid_tipo(self, client):
        resp = client.post("/api/documentos/templates", json={
            "nome": "Template",
            "tipo": "invalido",
            "conteudo": "Conteudo",
        })
        assert resp.status_code == 422
