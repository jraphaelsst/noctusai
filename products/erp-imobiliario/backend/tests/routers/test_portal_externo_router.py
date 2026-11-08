"""
Tests for the Portal Externo (Tenant/Owner Portal) router.
Covers link generation, token listing, token revocation, and public portal endpoints.
"""
import pytest
from datetime import datetime, timezone, timedelta

from noctusai_lib.api.auth.session.api_tokens import hash_token


class TestGerarLink:
    def test_gerar_link_proprietario(self, client):
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos Silva",
            "email": "carlos@test.com",
            "token_hash": hash_token("abc123"),
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
            "token_hash": hash_token("def456"),
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
            "token_hash": hash_token("ghi789"),
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

    def test_list_tokens_hides_raw_token(self, client):
        """SECURITY (Phase 6, N=2 absorption of Phase 3b portal_cliente defense):
        admin listing MUST NOT expose raw bearer tokens. Re-issue via /gerar-link.
        """
        client._mock_supabase.set_table_data("portal_tokens", [
            {
                "id": "pt1",
                "org_id": "test-org-123",
                "tipo": "proprietario",
                "pessoa_id": "p1",
                "nome": "Carlos",
                "email": "carlos@test.com",
                "token_hash": hash_token("MUST-NEVER-APPEAR-IN-LIST"),
                "is_active": True,
                "expires_at": "2026-08-11T00:00:00Z",
                "created_at": "2026-05-11",
            },
        ])
        resp = client.get("/api/portal/tokens")
        assert resp.status_code == 200
        body = resp.json()
        rows = body.get("data") or []
        assert rows, "expected at least one token in the listing"
        for row in rows:
            assert "token_hash" not in row and "token" not in row, (
                "PORTAL TOKEN LEAK at router boundary — admin listing "
                "/api/portal/tokens must hide raw bearer tokens."
            )

    def test_gerar_link_response_includes_token(self, client):
        """The one-shot issue at POST /gerar-link IS the only surface that shows
        the raw token. Pin that contract so admin listing absorption doesn't
        accidentally also hide it at issue time.
        """
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
            "token_hash": hash_token("ISSUED-AT-ONE-SHOT"),
            "is_active": True,
        })
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "token" in data
        assert "link" in data


class TestRevogarToken:
    def test_revoke_success(self, client):
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1", "org_id": "test-org-123", "is_active": False,
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
            "token_hash": hash_token("valid-token"),
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
            "org_id": "org-1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
            "token_hash": hash_token("tok-prop"),
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
            "org_id": "org-1",
            "tipo": "locatario",
            "pessoa_id": "p2",
            "nome": "Ana",
            "token_hash": hash_token("tok-loc"),
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
            "org_id": "org-1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
            "token_hash": hash_token("tok-fin"),
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
            "org_id": "org-1",
            "tipo": "locatario",
            "pessoa_id": "p2",
            "nome": "Ana",
            "token_hash": hash_token("tok-fin2"),
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
            "org_id": "org-1",
            "tipo": "locatario",
            "pessoa_id": "p1",
            "nome": "Ana",
            "token_hash": hash_token("tok-ctr"),
            "is_active": True,
            "expires_at": expires,
        })
        client._mock_supabase.set_table_data("contratos", [
            {"id": "ct1", "tipo": "locacao", "status": "ativo"},
        ])
        resp = client._tc.get("/api/portal/tok-ctr/contratos")
        assert resp.status_code == 200


class TestPortalDocumentos:
    """LGPD sharing-gate pinned tests (PROJECT.md erp-portal-documentos-sharing-gate).

    The production query at `portal_externo.py:portal_documentos` filters
    `compartilhado_portal=True`. These tests pin the contract: rows missing
    or with the flag False MUST NOT leak via the portal-cliente bearer token.
    """

    def test_documentos_success_returns_only_shared(self, client):
        """Filter-pin: only `compartilhado_portal=True` rows visible.

        MockSupabaseClient `.eq("compartilhado_portal", True)` applies the
        filter against the seeded list; non-shared rows are dropped. This
        pin guards against silent removal of the filter chain.
        """
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "org_id": "org-1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
            "token_hash": hash_token("tok-doc"),
            "is_active": True,
            "expires_at": expires,
        })
        client._mock_supabase.set_table_data("documentos", [
            {"id": "d1", "nome": "Contrato.pdf", "compartilhado_portal": True,
             "org_id": "org-1", "cliente_id": "p1"},
            {"id": "d2", "nome": "RG.pdf", "compartilhado_portal": False,
             "org_id": "org-1", "cliente_id": "p1"},
        ])
        resp = client._tc.get("/api/portal/tok-doc/documentos")
        assert resp.status_code == 200
        body = resp.json()
        # `success_response` wraps payload under "data"; the filter MUST
        # drop d2 (False) and surface only d1 (True).
        rows = body.get("data") or []
        ids = [r.get("id") for r in rows]
        assert "d1" in ids, f"shared doc d1 should be returned, got {ids}"
        assert "d2" not in ids, f"private doc d2 MUST NOT leak via portal, got {ids}"

    def test_documentos_empty_when_none_shared(self, client):
        """All rows have `compartilhado_portal=False` → empty result."""
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "org_id": "org-1",
            "tipo": "locatario",
            "pessoa_id": "p2",
            "nome": "Ana",
            "token_hash": hash_token("tok-doc2"),
            "is_active": True,
            "expires_at": expires,
        })
        client._mock_supabase.set_table_data("documentos", [
            {"id": "d3", "nome": "Privado.pdf", "compartilhado_portal": False,
             "org_id": "org-1", "cliente_id": "p2"},
        ])
        resp = client._tc.get("/api/portal/tok-doc2/documentos")
        assert resp.status_code == 200
        body = resp.json()
        rows = body.get("data") or []
        assert rows == [], f"expected zero leak, got {rows}"

    def test_documentos_empty_table(self, client):
        """Empty table → empty data list, no audit-log on zero rows still fires."""
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client._mock_supabase.set_table_data("portal_tokens", {
            "id": "pt1",
            "org_id": "org-1",
            "tipo": "locatario",
            "pessoa_id": "p2",
            "nome": "Ana",
            "token_hash": hash_token("tok-doc3"),
            "is_active": True,
            "expires_at": expires,
        })
        client._mock_supabase.set_table_data("documentos", [])
        resp = client._tc.get("/api/portal/tok-doc3/documentos")
        assert resp.status_code == 200


def _row(raw, *, active=True, days=30):
    return {
        "id": "pt1", "org_id": "org-1", "tipo": "proprietario", "pessoa_id": "p1",
        "nome": "Carlos", "token_hash": hash_token(raw), "is_active": active,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
    }


class TestTokenHashedAtRest:
    def test_issue_persists_only_hash_and_returns_raw_once(self, client):
        client._mock_supabase.set_table_data("portal_tokens", [])
        resp = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario", "pessoa_id": "p1", "nome": "Carlos",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        raw = data["token"]
        assert data["link"] == f"/portal/{raw}"
        payloads = client._mock_supabase.table("portal_tokens").inserted_payloads
        assert len(payloads) == 1
        assert "token" not in payloads[0]
        assert payloads[0]["token_hash"] == hash_token(raw)
        assert raw not in repr(payloads[0])

    def test_issue_then_validate_ok(self, client):
        client._mock_supabase.set_table_data("portal_tokens", [])
        raw = client.post("/api/portal/gerar-link", json={
            "tipo": "proprietario", "pessoa_id": "p1", "nome": "Carlos",
        }).json()["data"]["token"]
        stored = client._mock_supabase.table("portal_tokens").inserted_payloads[0]
        client._mock_supabase.set_table_data("portal_tokens", [{**stored, "id": "pt1"}])
        assert client._tc.get(f"/api/portal/{raw}").status_code == 200

    def test_wrong_token_refused(self, client):
        client._mock_supabase.set_table_data("portal_tokens", [_row("right")])
        assert client._tc.get("/api/portal/wrong").status_code == 404

    def test_plaintext_hash_is_not_a_credential(self, client):
        client._mock_supabase.set_table_data("portal_tokens", [_row("right")])
        assert client._tc.get(f"/api/portal/{hash_token('right')}").status_code == 404

    def test_inactive_token_refused(self, client):
        client._mock_supabase.set_table_data("portal_tokens", [_row("tok", active=False)])
        assert client._tc.get("/api/portal/tok").status_code == 404

    def test_expired_token_refused_401(self, client):
        client._mock_supabase.set_table_data("portal_tokens", [_row("tok", days=-1)])
        assert client._tc.get("/api/portal/tok").status_code == 401

    def test_gerar_link_requires_auth_401(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        resp = TestClient(app).post("/api/portal/gerar-link", json={
            "tipo": "proprietario", "pessoa_id": "p1", "nome": "Carlos",
        })
        assert resp.status_code == 401
