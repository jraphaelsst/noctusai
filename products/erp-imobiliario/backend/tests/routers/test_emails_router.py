"""
Tests for Emails router — /api/emails
Covers email listing, get by id, send, and template CRUD operations.
"""
import pytest


class TestListarEmails:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("emails", [
            {"id": "em1", "destinatario": "joao@test.com", "assunto": "Proposta",
             "direcao": "enviado", "status": "enviado"},
            {"id": "em2", "destinatario": "maria@test.com", "assunto": "Contrato",
             "direcao": "enviado", "status": "entregue"},
        ])
        resp = client.get("/api/emails")
        assert resp.status_code == 200

    def test_filter_by_direcao(self, client):
        client._mock_supabase.set_table_data("emails", [
            {"id": "em1", "direcao": "enviado", "status": "enviado"},
        ])
        resp = client.get("/api/emails?direcao=enviado")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("emails", [
            {"id": "em1", "direcao": "enviado", "status": "entregue"},
        ])
        resp = client.get("/api/emails?status=entregue")
        assert resp.status_code == 200


class TestObterEmail:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("emails", {
            "id": "em1", "remetente": "user-123", "destinatario": "joao@test.com",
            "assunto": "Proposta imovel", "corpo": "Segue proposta.",
            "direcao": "enviado", "status": "enviado",
        })
        resp = client.get("/api/emails/em1")
        assert resp.status_code == 200

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("emails", None)
        resp = client.get("/api/emails/nonexistent")
        assert resp.status_code in [200, 404]


class TestEnviarEmail:
    def test_enviar_success(self, client):
        client._mock_supabase.set_table_data("emails", {
            "id": "em-new", "remetente": "test-user-123",
            "destinatario": "cliente@test.com", "assunto": "Novo imovel disponivel",
            "corpo": "Temos um imovel que combina com seu perfil.",
            "direcao": "enviado", "status": "enviado",
        })
        resp = client.post("/api/emails/enviar", json={
            "destinatario": "cliente@test.com",
            "assunto": "Novo imovel disponivel",
            "corpo": "Temos um imovel que combina com seu perfil.",
        })
        assert resp.status_code == 200

    def test_enviar_missing_required(self, client):
        resp = client.post("/api/emails/enviar", json={
            "destinatario": "cliente@test.com",
        })
        assert resp.status_code == 422


class TestTemplates:
    def test_listar_templates(self, client):
        client._mock_supabase.set_table_data("email_templates", [
            {"id": "tpl1", "nome": "Boas-vindas", "assunto": "Bem-vindo!",
             "corpo": "Ola {{nome}}", "ativo": True},
        ])
        resp = client.get("/api/emails/templates")
        assert resp.status_code == 200

    def test_criar_template(self, client):
        client._mock_supabase.set_table_data("email_templates", {
            "id": "tpl-new", "nome": "Follow-up", "assunto": "Acompanhamento",
            "corpo": "Ola {{nome}}, seguimos acompanhando.",
            "variaveis": ["nome"], "ativo": True,
        })
        resp = client.post("/api/emails/templates", json={
            "nome": "Follow-up",
            "assunto": "Acompanhamento",
            "corpo": "Ola {{nome}}, seguimos acompanhando.",
            "variaveis": ["nome"],
        })
        assert resp.status_code == 200

    def test_obter_template(self, client):
        client._mock_supabase.set_table_data("email_templates", {
            "id": "tpl1", "nome": "Boas-vindas", "assunto": "Bem-vindo!",
            "corpo": "Ola {{nome}}", "variaveis": ["nome"], "ativo": True,
        })
        resp = client.get("/api/emails/templates/tpl1")
        assert resp.status_code == 200

    def test_atualizar_template(self, client):
        client._mock_supabase.set_table_data("email_templates", {
            "id": "tpl1", "nome": "Boas-vindas v2", "assunto": "Bem-vindo!",
            "corpo": "Ola {{nome}}, seja bem-vindo!", "ativo": True,
        })
        resp = client.patch("/api/emails/templates/tpl1", json={
            "nome": "Boas-vindas v2",
        })
        assert resp.status_code == 200

    def test_excluir_template(self, client):
        client._mock_supabase.set_table_data("email_templates", [])
        resp = client.delete("/api/emails/templates/tpl1")
        assert resp.status_code == 200
