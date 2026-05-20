"""
Tests for Portal do Cliente router — /api/portal-cliente
"""
import pytest
from unittest.mock import patch, MagicMock


class TestGerarAcesso:
    def test_gerar_success(self, client):
        client._mock_supabase.set_table_data("portal_acessos", {
            "id": "pa1",
            "cliente_id": "c1",
            "token": "tok-abc123",
            "ativo": True,
        })
        with patch(
            "app.routers.portal_cliente.PortalClienteService.gerar_token",
            return_value="tok-abc123",
        ):
            resp = client.post("/api/portal-cliente/gerar-acesso", json={
                "cliente_id": "c1",
            })
            assert resp.status_code == 200

    def test_gerar_with_expiracao(self, client):
        client._mock_supabase.set_table_data("portal_acessos", {
            "id": "pa2",
            "cliente_id": "c1",
            "token": "tok-xyz",
            "ativo": True,
            "data_expiracao": "2027-01-01T00:00:00Z",
        })
        with patch(
            "app.routers.portal_cliente.PortalClienteService.gerar_token",
            return_value="tok-xyz",
        ):
            resp = client.post("/api/portal-cliente/gerar-acesso", json={
                "cliente_id": "c1",
                "data_expiracao": "2027-01-01T00:00:00Z",
            })
            assert resp.status_code == 200

    def test_missing_cliente_id(self, client):
        resp = client.post("/api/portal-cliente/gerar-acesso", json={})
        assert resp.status_code == 422


class TestListarAcessos:
    def test_list_acessos(self, client):
        client._mock_supabase.set_table_data("portal_acessos", [
            {"id": "pa1", "cliente_id": "c1", "token": "tok1", "ativo": True},
            {"id": "pa2", "cliente_id": "c2", "token": "tok2", "ativo": True},
        ])
        resp = client.get("/api/portal-cliente/acessos")
        assert resp.status_code == 200

    def test_list_acessos_filter_by_cliente(self, client):
        client._mock_supabase.set_table_data("portal_acessos", [
            {"id": "pa1", "cliente_id": "c1", "token": "tok1", "ativo": True},
        ])
        resp = client.get("/api/portal-cliente/acessos?cliente_id=c1")
        assert resp.status_code == 200

    def test_list_acessos_hides_raw_token(self, client):
        """SECURITY (Phase 3b → Phase 6 router-boundary pin):
        admin /acessos listing MUST NOT expose raw portal bearer tokens.
        Re-issue via POST /gerar-acesso instead.
        """
        client._mock_supabase.set_table_data("portal_acessos", [
            {
                "id": "pa1",
                "cliente_id": "c1",
                "token": "MUST-NEVER-APPEAR-IN-LIST",
                "ativo": True,
                "created_at": "2026-05-11",
            },
        ])
        resp = client.get("/api/portal-cliente/acessos")
        assert resp.status_code == 200
        body = resp.json()
        rows = body.get("data") or []
        assert rows, "expected at least one acesso in the listing"
        for row in rows:
            assert "token" not in row, (
                "PORTAL TOKEN LEAK at router boundary — admin listing "
                "/api/portal-cliente/acessos must hide raw bearer tokens."
            )


class TestRevogarAcesso:
    def test_revoke_success(self, client):
        client._mock_supabase.set_table_data("portal_acessos", {
            "id": "pa1", "ativo": False,
        })
        resp = client.delete("/api/portal-cliente/acessos/pa1")
        assert resp.status_code == 200

    def test_revoke_not_found(self, client):
        client._mock_supabase.set_table_data("portal_acessos", None)
        resp = client.delete("/api/portal-cliente/acessos/nonexistent")
        assert resp.status_code == 404


class TestChamados:
    def test_listar_chamados(self, client):
        client._mock_supabase.set_table_data("chamados_portal", [
            {"id": "ch1", "assunto": "Problema no boleto", "status": "aberto"},
            {"id": "ch2", "assunto": "Duvida contrato", "status": "resolvido"},
        ])
        resp = client.get("/api/portal-cliente/chamados")
        assert resp.status_code == 200

    def test_listar_chamados_filter_by_status(self, client):
        client._mock_supabase.set_table_data("chamados_portal", [
            {"id": "ch1", "assunto": "Problema", "status": "aberto"},
        ])
        resp = client.get("/api/portal-cliente/chamados?status=aberto")
        assert resp.status_code == 200

    def test_listar_chamados_filter_by_cliente(self, client):
        client._mock_supabase.set_table_data("chamados_portal", [
            {"id": "ch1", "assunto": "Duvida", "cliente_id": "c1"},
        ])
        resp = client.get("/api/portal-cliente/chamados?cliente_id=c1")
        assert resp.status_code == 200

    def test_update_chamado(self, client):
        client._mock_supabase.set_table_data("chamados_portal", {
            "id": "ch1", "status": "resolvido", "resposta": "Resolvido",
        })
        resp = client.patch("/api/portal-cliente/chamados/ch1", json={
            "status": "resolvido",
            "resposta": "Problema corrigido",
        })
        assert resp.status_code == 200

    def test_update_chamado_empty_body(self, client):
        resp = client.patch("/api/portal-cliente/chamados/ch1", json={})
        assert resp.status_code == 400

    def test_update_chamado_not_found(self, client):
        client._mock_supabase.set_table_data("chamados_portal", None)
        resp = client.patch("/api/portal-cliente/chamados/ch1", json={
            "status": "fechado",
        })
        assert resp.status_code == 404


class TestPortalPublico:
    """Tests for client-facing (token-based, no Bearer auth) endpoints."""

    def test_dashboard(self, client):
        mock_acesso = {
            "id": "pa1",
            "cliente_id": "c1",
            "org_id": "org1",
            "token": "valid-token",
            "ativo": True,
        }
        mock_dashboard = {
            "contratos": [{"id": "ct1"}],
            "financeiro": [{"id": "ln1"}],
            "documentos": [],
        }
        with patch(
            "app.routers.portal_cliente.PortalClienteService.__from_token__",
        ) as mock_factory:
            mock_service = MagicMock()
            mock_service.validar_token.return_value = mock_acesso
            mock_service.get_dashboard.return_value = mock_dashboard
            mock_factory.return_value = mock_service

            resp = client._tc.get("/api/portal-cliente/valid-token/dashboard")
            assert resp.status_code == 200

    def test_financeiro(self, client):
        mock_acesso = {
            "id": "pa1",
            "cliente_id": "c1",
            "org_id": "org1",
            "token": "valid-token",
            "ativo": True,
        }
        with patch(
            "app.routers.portal_cliente.PortalClienteService.__from_token__",
        ) as mock_factory:
            mock_service = MagicMock()
            mock_service.validar_token.return_value = mock_acesso
            mock_service.get_financeiro.return_value = [
                {"id": "ln1", "valor": 1500.00, "status": "pago"},
            ]
            mock_factory.return_value = mock_service

            resp = client._tc.get("/api/portal-cliente/valid-token/financeiro")
            assert resp.status_code == 200

    def test_chamados(self, client):
        mock_acesso = {
            "id": "pa1",
            "cliente_id": "c1",
            "org_id": "org1",
            "token": "valid-token",
            "ativo": True,
        }
        with patch(
            "app.routers.portal_cliente.PortalClienteService.__from_token__",
        ) as mock_factory:
            mock_service = MagicMock()
            mock_service.validar_token.return_value = mock_acesso
            mock_service.get_chamados.return_value = [
                {"id": "ch1", "assunto": "Duvida", "status": "aberto"},
            ]
            mock_factory.return_value = mock_service

            resp = client._tc.get("/api/portal-cliente/valid-token/chamados")
            assert resp.status_code == 200

    def test_criar_chamado(self, client):
        mock_acesso = {
            "id": "pa1",
            "cliente_id": "c1",
            "org_id": "org1",
            "token": "valid-token",
            "ativo": True,
        }
        with patch(
            "app.routers.portal_cliente.PortalClienteService.__from_token__",
        ) as mock_factory:
            mock_service = MagicMock()
            mock_service.validar_token.return_value = mock_acesso
            mock_service.db = client._mock_supabase

            client._mock_supabase.set_table_data("chamados_portal", {
                "id": "ch-new",
                "assunto": "Vazamento",
                "descricao": "Torneira vazando na cozinha",
                "status": "aberto",
                "prioridade": "alta",
            })

            mock_factory.return_value = mock_service

            resp = client._tc.post("/api/portal-cliente/valid-token/chamados", json={
                "assunto": "Vazamento",
                "descricao": "Torneira vazando na cozinha",
                "prioridade": "alta",
            })
            assert resp.status_code == 200

    def test_criar_chamado_missing_fields(self, client):
        mock_acesso = {
            "id": "pa1",
            "cliente_id": "c1",
            "org_id": "org1",
            "token": "valid-token",
            "ativo": True,
        }
        with patch(
            "app.routers.portal_cliente.PortalClienteService.__from_token__",
        ) as mock_factory:
            mock_service = MagicMock()
            mock_service.validar_token.return_value = mock_acesso
            mock_factory.return_value = mock_service

            resp = client._tc.post("/api/portal-cliente/valid-token/chamados", json={})
            assert resp.status_code == 422
