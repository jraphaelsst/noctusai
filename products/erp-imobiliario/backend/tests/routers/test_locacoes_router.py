"""
Tests for Locacoes (lease contracts) router — /api/locacoes
"""
import pytest
from unittest.mock import patch


class TestListarContratos:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", [
            {"id": "cl1", "imovel_id": "im1", "locatario_id": "loc1", "valor_aluguel": 2500, "status": "ativo"},
            {"id": "cl2", "imovel_id": "im2", "locatario_id": "loc2", "valor_aluguel": 3000, "status": "encerrado"},
        ])
        resp = client.get("/api/locacoes")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", [
            {"id": "cl1", "valor_aluguel": 2500, "status": "ativo"},
        ])
        resp = client.get("/api/locacoes?status=ativo")
        assert resp.status_code == 200

    def test_list_with_pagination(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", [
            {"id": "cl1", "valor_aluguel": 2500, "status": "ativo"},
        ])
        resp = client.get("/api/locacoes?page=1&page_size=10")
        assert resp.status_code == 200


class TestCriarContrato:
    def test_create_success(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl-new",
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "valor_aluguel": 2500,
            "data_inicio": "2026-03-01",
            "data_fim": "2027-03-01",
            "status": "ativo",
        })
        resp = client.post("/api/locacoes", json={
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "valor_aluguel": 2500,
            "data_inicio": "2026-03-01",
            "data_fim": "2027-03-01",
        })
        assert resp.status_code == 200

    def test_create_with_all_fields(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl-full",
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "proprietario_id": "prop1",
            "valor_aluguel": 3500,
            "dia_vencimento": 15,
            "data_inicio": "2026-03-01",
            "data_fim": "2027-03-01",
            "indice_reajuste": "IPCA",
            "taxa_administracao": 8.0,
            "valor_caucao": 7000,
            "observacoes": "Contrato renovavel",
        })
        resp = client.post("/api/locacoes", json={
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "proprietario_id": "prop1",
            "valor_aluguel": 3500,
            "dia_vencimento": 15,
            "data_inicio": "2026-03-01",
            "data_fim": "2027-03-01",
            "indice_reajuste": "IPCA",
            "taxa_administracao": 8.0,
            "valor_caucao": 7000,
            "observacoes": "Contrato renovavel",
        })
        assert resp.status_code == 200

    def test_create_missing_required(self, client):
        resp = client.post("/api/locacoes", json={})
        assert resp.status_code == 422

    def test_create_invalid_dates_end_before_start(self, client):
        resp = client.post("/api/locacoes", json={
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "valor_aluguel": 2500,
            "data_inicio": "2027-03-01",
            "data_fim": "2026-03-01",
        })
        assert resp.status_code == 400

    def test_create_invalid_date_format(self, client):
        resp = client.post("/api/locacoes", json={
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "valor_aluguel": 2500,
            "data_inicio": "invalid",
            "data_fim": "2027-03-01",
        })
        assert resp.status_code == 400

    def test_create_negative_valor(self, client):
        resp = client.post("/api/locacoes", json={
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "valor_aluguel": -100,
            "data_inicio": "2026-03-01",
            "data_fim": "2027-03-01",
        })
        assert resp.status_code == 422


class TestObterContrato:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl1",
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "valor_aluguel": 2500,
            "status": "ativo",
        })
        resp = client.get("/api/locacoes/cl1")
        assert resp.status_code == 200

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", None)
        resp = client.get("/api/locacoes/nonexistent")
        assert resp.status_code == 404


class TestAtualizarContrato:
    def test_update_success(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl1", "valor_aluguel": 2800, "status": "ativo",
        })
        resp = client.patch("/api/locacoes/cl1", json={
            "valor_aluguel": 2800,
        })
        assert resp.status_code == 200

    def test_update_status(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl1", "status": "inadimplente",
        })
        resp = client.patch("/api/locacoes/cl1", json={
            "status": "inadimplente",
        })
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/locacoes/cl1", json={})
        assert resp.status_code == 400

    def test_update_not_found(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", None)
        resp = client.patch("/api/locacoes/cl1", json={
            "valor_aluguel": 3000,
        })
        assert resp.status_code == 404


class TestExcluirContrato:
    def test_delete(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", [{"id": "cl1"}])
        resp = client.delete("/api/locacoes/cl1")
        assert resp.status_code == 200

    def test_delete_not_found(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", [])
        resp = client.delete("/api/locacoes/nonexistent")
        assert resp.status_code == 404


class TestReajuste:
    def test_reajuste_preview(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl1",
            "valor_aluguel": 2500,
            "indice_reajuste": "IGPM",
        })
        with patch(
            "app.routers.locacoes.calculate_reajuste",
            return_value={
                "valor_anterior": 2500,
                "valor_novo": 2613.0,
                "diferenca": 113.0,
                "indice": "IGPM",
                "percentual_aplicado": 4.52,
            },
        ):
            resp = client.post("/api/locacoes/cl1/reajuste", json={
                "aplicar": False,
            })
            assert resp.status_code == 200

    def test_reajuste_apply(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl1",
            "valor_aluguel": 2500,
            "indice_reajuste": "IGPM",
        })
        with patch(
            "app.routers.locacoes.calculate_reajuste",
            return_value={
                "valor_anterior": 2500,
                "valor_novo": 2613.0,
                "diferenca": 113.0,
                "indice": "IGPM",
                "percentual_aplicado": 4.52,
            },
        ):
            resp = client.post("/api/locacoes/cl1/reajuste", json={
                "aplicar": True,
            })
            assert resp.status_code == 200

    def test_reajuste_with_custom_percentual(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl1",
            "valor_aluguel": 2500,
            "indice_reajuste": "fixo",
        })
        with patch(
            "app.routers.locacoes.calculate_reajuste",
            return_value={
                "valor_anterior": 2500,
                "valor_novo": 2625.0,
                "diferenca": 125.0,
                "indice": "fixo",
                "percentual_aplicado": 5.0,
            },
        ):
            resp = client.post("/api/locacoes/cl1/reajuste", json={
                "percentual": 5.0,
                "aplicar": False,
            })
            assert resp.status_code == 200

    def test_reajuste_contrato_not_found(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", None)
        resp = client.post("/api/locacoes/nonexistent/reajuste", json={
            "aplicar": False,
        })
        assert resp.status_code == 404


class TestRenovarContrato:
    def test_renovar_success(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl1",
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "proprietario_id": "prop1",
            "valor_aluguel": 2500,
            "dia_vencimento": 10,
            "data_inicio": "2025-03-01",
            "data_fim": "2026-03-01",
            "indice_reajuste": "IGPM",
            "percentual_reajuste": 4.52,
            "taxa_administracao": 10.0,
            "valor_caucao": 5000,
            "status": "ativo",
        })
        resp = client.post("/api/locacoes/cl1/renovar", json={
            "nova_data_fim": "2027-03-01",
        })
        assert resp.status_code == 200

    def test_renovar_with_new_valor(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl1",
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "valor_aluguel": 2500,
            "dia_vencimento": 10,
            "data_inicio": "2025-03-01",
            "data_fim": "2026-03-01",
            "indice_reajuste": "IGPM",
            "taxa_administracao": 10.0,
            "status": "ativo",
        })
        resp = client.post("/api/locacoes/cl1/renovar", json={
            "nova_data_fim": "2027-03-01",
            "novo_valor": 2800,
        })
        assert resp.status_code == 200

    def test_renovar_contrato_not_found(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", None)
        resp = client.post("/api/locacoes/nonexistent/renovar", json={
            "nova_data_fim": "2027-03-01",
        })
        assert resp.status_code == 404

    def test_renovar_invalid_date(self, client):
        client._mock_supabase.set_table_data("contratos_locacao", {
            "id": "cl1",
            "imovel_id": "im1",
            "locatario_id": "loc1",
            "valor_aluguel": 2500,
            "dia_vencimento": 10,
            "data_inicio": "2025-03-01",
            "data_fim": "2026-03-01",
            "indice_reajuste": "IGPM",
            "status": "ativo",
        })
        resp = client.post("/api/locacoes/cl1/renovar", json={
            "nova_data_fim": "2025-01-01",
        })
        assert resp.status_code == 400

    def test_renovar_missing_nova_data_fim(self, client):
        resp = client.post("/api/locacoes/cl1/renovar", json={})
        assert resp.status_code == 422
