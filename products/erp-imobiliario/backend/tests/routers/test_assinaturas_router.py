"""
Tests for Assinaturas (digital signatures) router — /api/assinaturas
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestListarAssinaturas:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("assinaturas", [
            {"id": "a1", "documento_nome": "Contrato de Venda", "status": "enviado"},
            {"id": "a2", "documento_nome": "Procuração", "status": "assinado"},
        ])
        resp = client.get("/api/assinaturas")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("assinaturas", [
            {"id": "a1", "documento_nome": "Contrato", "status": "pendente"},
        ])
        resp = client.get("/api/assinaturas?status=pendente")
        assert resp.status_code == 200

    def test_filter_by_contrato_id(self, client):
        client._mock_supabase.set_table_data("assinaturas", [
            {"id": "a1", "documento_nome": "Contrato", "contrato_id": "ct1"},
        ])
        resp = client.get("/api/assinaturas?contrato_id=ct1")
        assert resp.status_code == 200


class TestEnviarAssinatura:
    def test_enviar_success(self, client):
        client._mock_supabase.set_table_data("assinaturas", {
            "id": "new-a",
            "documento_nome": "Contrato de Locação",
            "status": "enviado",
            "signatarios": [{"nome": "João", "email": "joao@test.com", "papel": "locatario"}],
        })
        with patch(
            "app.routers.assinaturas.AssinaturaService.preparar_envio",
            new_callable=AsyncMock,
            return_value={
                "id": "new-a",
                "documento_nome": "Contrato de Locação",
                "status": "enviado",
            },
        ):
            resp = client.post("/api/assinaturas/enviar", json={
                "documento_nome": "Contrato de Locação",
                "signatarios": [
                    {"nome": "João", "email": "joao@test.com", "papel": "locatario"},
                ],
            })
            assert resp.status_code == 200

    def test_enviar_missing_fields(self, client):
        resp = client.post("/api/assinaturas/enviar", json={})
        assert resp.status_code == 422

    def test_enviar_missing_signatarios(self, client):
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato de Venda",
        })
        assert resp.status_code == 422

    def test_enviar_empty_signatarios(self, client):
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato de Venda",
            "signatarios": [],
        })
        assert resp.status_code == 422


class TestObterAssinatura:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("assinaturas", {
            "id": "a1",
            "documento_nome": "Contrato",
            "status": "enviado",
            "signatarios": [],
            "historico": [],
        })
        resp = client.get("/api/assinaturas/a1")
        assert resp.status_code == 200

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("assinaturas", None)
        resp = client.get("/api/assinaturas/nonexistent")
        assert resp.status_code == 404


class TestWebhook:
    def test_webhook_success(self, client):
        with patch(
            "app.routers.assinaturas.get_admin_client",
            return_value=client._mock_supabase,
        ), patch(
            "app.routers.assinaturas.AssinaturaService.processar_webhook",
            new_callable=AsyncMock,
            return_value={"id": "a1", "status": "assinado"},
        ):
            resp = client._tc.post("/api/assinaturas/webhook", json={
                "assinatura_id": "a1",
                "evento": "assinado",
            })
            assert resp.status_code == 200

    def test_webhook_missing_fields(self, client):
        resp = client._tc.post("/api/assinaturas/webhook", json={})
        assert resp.status_code == 422


class TestCancelarAssinatura:
    def test_cancel_success(self, client):
        with patch(
            "app.routers.assinaturas.AssinaturaService.cancelar",
            new_callable=AsyncMock,
            return_value={"id": "a1", "status": "cancelado"},
        ):
            resp = client.delete("/api/assinaturas/a1")
            assert resp.status_code == 200

    def test_cancel_not_found(self, client):
        with patch(
            "app.routers.assinaturas.AssinaturaService.cancelar",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.delete("/api/assinaturas/nonexistent")
            assert resp.status_code == 404


class TestResumoAssinaturas:
    def test_resumo(self, client):
        client._mock_supabase.set_table_data("assinaturas", [
            {"id": "a1", "status": "enviado"},
            {"id": "a2", "status": "assinado"},
            {"id": "a3", "status": "pendente"},
        ])
        with patch(
            "app.routers.assinaturas.AssinaturaService.get_resumo",
            return_value={
                "pendentes": 1,
                "enviadas": 1,
                "assinadas": 1,
                "recusadas": 0,
                "expiradas": 0,
                "canceladas": 0,
                "total": 3,
            },
        ):
            resp = client.get("/api/assinaturas/resumo")
            assert resp.status_code == 200
