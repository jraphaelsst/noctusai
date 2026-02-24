"""
Tests for the Portal Externo (Tenant/Owner Portal) router.
Covers link generation, token listing, token revocation, and public portal endpoints.
"""
import pytest
from datetime import datetime, timezone, timedelta


class TestGerarLink:
    def test_gerar_link_proprietario(self, client):
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos Silva",
            "email": "carlos@test.com",
            "token": "abc123",
            "is_active": True,
        })
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos Silva",
            "email": "carlos@test.com",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "link" in data

    def test_gerar_link_locatario(self, client):
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt2",
            "tipo": "locatario",
            "pessoa_id": "p2",
            "nome": "Ana Costa",
            "token": "def456",
            "is_active": True,
        })
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "locatario",
            "pessoa_id": "p2",
            "nome": "Ana Costa",
        })
        assert resp.status_code == 200

    def test_gerar_link_custom_validade(self, client):
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt3",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "João",
            "token": "ghi789",
            "is_active": True,
        })
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "João",
            "dias_validade": 30,
        })
        assert resp.status_code == 200

    def test_gerar_link_invalid_tipo(self, client):
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "invalido",
            "pessoa_id": "p1",
            "nome": "Test",
        })
        assert resp.status_code == 422

    def test_gerar_link_missing_nome(self, client):
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario",
            "pessoa_id": "p1",
        })
        assert resp.status_code == 422

    def test_gerar_link_missing_pessoa_id(self, client):
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario",
            "nome": "Test",
        })
        assert resp.status_code == 422

    def test_gerar_link_empty_nome(self, client):
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "",
        })
        assert resp.status_code == 422

    def test_gerar_link_validade_too_high(self, client):
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Test",
            "dias_validade": 999,
        })
        assert resp.status_code == 422

    def test_gerar_link_validade_zero(self, client):
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Test",
            "dias_validade": 0,
        })
        assert resp.status_code == 422


class TestListarTokens:
    def test_list_tokens(self, client):
        client._mock_supabase.set_table_data("portal_tokens", [
            {"id": "pt1", "tipo": "proprietario", "nome": "Carlos", "is_active": True},
            {"id": "pt2", "tipo": "locatario", "nome": "Ana", "is_active": True},
        ])
        resp = client.get("/api/portal/tokens")
        assert resp.status_code == 200

    def test_list_tokens_pagination(self, client):
        client._mock_supabase.set_table_data("portal_tokens", [])
        resp = client.get("/api/portal/tokens?page=1&page_size=10")
        assert resp.status_code == 200

    def test_list_tokens_empty(self, client):
        client._mock_supabase.set_table_data("portal_tokens", [])
        resp = client.get("/api/portal/tokens")
        assert resp.status_code == 200


class TestRevogarToken:
    def test_revoke_success(self, client):
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1", "is_active": False,
        })
        resp = client.delete("/api/portal/tokens/pt1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_revoke_not_found(self, client):
        client._mock_supabase.set_table_data("portal_tokens", None)
        resp = client.delete("/api/portal/tokens/nonexistent")
        assert resp.status_code == 404


class TestValidarPortal:
    def test_validar_token_success(self, client):
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "tipo": "proprietario",
            "nome": "Carlos",
            "pessoa_id": "p1",
            "token": "valid-token",
            "is_active": True,
            "expires_at": expires,
        })
        resp = client._tc.get("/api/portal/valid-token")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["tipo"] == "proprietario"
        assert data["nome"] == "Carlos"

    def test_validar_token_not_found(self, client):
        client._mock_supabase.set_table_data("portal_tokens", None)
        resp = client._tc.get("/api/portal/invalid-token")
        assert resp.status_code == 404


class TestPortalImoveis:
    def test_imoveis_proprietario(self, client):
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
            "token": "tok-prop",
            "is_active": True,
            "expires_at": expires,
        })
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a1", "tipo_imovel": "apartamento", "cidade": "SP", "valor": 500000},
            {"id": "a2", "tipo_imovel": "casa", "cidade": "RJ", "valor": 800000},
        ])
        resp = client._tc.get("/api/portal/tok-prop/imoveis")
        assert resp.status_code == 200

    def test_imoveis_locatario_forbidden(self, client):
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt2",
            "tipo": "locatario",
            "pessoa_id": "p2",
            "nome": "Ana",
            "token": "tok-loc",
            "is_active": True,
            "expires_at": expires,
        })
        resp = client._tc.get("/api/portal/tok-loc/imoveis")
        assert resp.status_code == 403


class TestPortalFinanceiro:
    def test_financeiro_proprietario(self, client):
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
            "token": "tok-fin",
            "is_active": True,
            "expires_at": expires,
        })
        client._mock_supabase.set_table_data("financeiro", [
            {"id": "f1", "valor": 3000, "tipo": "aluguel"},
        ])
        resp = client._tc.get("/api/portal/tok-fin/financeiro")
        assert resp.status_code == 200

    def test_financeiro_locatario_forbidden(self, client):
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt2",
            "tipo": "locatario",
            "pessoa_id": "p2",
            "nome": "Ana",
            "token": "tok-fin2",
            "is_active": True,
            "expires_at": expires,
        })
        resp = client._tc.get("/api/portal/tok-fin2/financeiro")
        assert resp.status_code == 403


class TestPortalContratos:
    def test_contratos_success(self, client):
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "tipo": "locatario",
            "pessoa_id": "p1",
            "nome": "Ana",
            "token": "tok-ctr",
            "is_active": True,
            "expires_at": expires,
        })
        client._mock_supabase.set_table_data("contratos", [
            {"id": "ct1", "tipo": "locacao", "status": "ativo"},
        ])
        resp = client._tc.get("/api/portal/tok-ctr/contratos")
        assert resp.status_code == 200


class TestPortalDocumentos:
    def test_documentos_success(self, client):
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
            "token": "tok-doc",
            "is_active": True,
            "expires_at": expires,
        })
        client._mock_supabase.set_table_data("documentos", [
            {"id": "d1", "nome": "Contrato.pdf", "compartilhado_portal": True},
        ])
        resp = client._tc.get("/api/portal/tok-doc/documentos")
        assert resp.status_code == 200

    def test_documentos_empty(self, client):
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "tipo": "locatario",
            "pessoa_id": "p2",
            "nome": "Ana",
            "token": "tok-doc2",
            "is_active": True,
            "expires_at": expires,
        })
        client._mock_supabase.set_table_data("documentos", [])
        resp = client._tc.get("/api/portal/tok-doc2/documentos")
        assert resp.status_code == 200
