"""
Tests for the AI Features router.
Covers property description generation, lead scoring, and price suggestion endpoints.
"""
import pytest
from unittest.mock import patch, AsyncMock


class TestGenerateDescription:
    def test_generate_with_imovel_id(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "tipo_imovel": "apartamento",
            "cidade": "Sao Paulo",
            "bairro": "Jardins",
            "area_privativa": 120,
            "quartos": 3,
            "suites": 1,
            "vagas": 2,
            "valor": 800000,
        })
        with patch(
            "app.services.ai_service.generate_description",
            new_callable=AsyncMock,
            return_value={
                "titulo_sugerido": "Lindo apartamento no Jardins",
                "descricao": "Excelente apartamento com 3 quartos...",
            },
        ):
            resp = client.post("/api/ai/generate-description", json={
                "imovel_id": "a1",
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert "titulo_sugerido" in data
            assert "descricao" in data

    def test_generate_with_imovel_data(self, client):
        with patch(
            "app.services.ai_service.generate_description",
            new_callable=AsyncMock,
            return_value={
                "titulo_sugerido": "Casa ampla em Alphaville",
                "descricao": "Casa espacosa com 4 quartos...",
            },
        ):
            resp = client.post("/api/ai/generate-description", json={
                "imovel_data": {
                    "tipo_imovel": "casa",
                    "cidade": "Barueri",
                    "bairro": "Alphaville",
                    "quartos": 4,
                    "valor": 1500000,
                },
            })
            assert resp.status_code == 200

    def test_generate_no_data(self, client):
        resp = client.post("/api/ai/generate-description", json={})
        assert resp.status_code == 400

    def test_generate_imovel_not_found(self, client):
        client._mock_supabase.set_table_data("ativos", None)
        resp = client.post("/api/ai/generate-description", json={
            "imovel_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_generate_ai_service_error(self, client):
        with patch(
            "app.services.ai_service.generate_description",
            new_callable=AsyncMock,
            side_effect=Exception("OpenAI API error"),
        ):
            resp = client.post("/api/ai/generate-description", json={
                "imovel_data": {
                    "tipo_imovel": "casa",
                    "quartos": 3,
                },
            })
            assert resp.status_code == 500

    def test_generate_ai_value_error(self, client):
        with patch(
            "app.services.ai_service.generate_description",
            new_callable=AsyncMock,
            side_effect=ValueError("Chave da API OpenAI nao configurada"),
        ):
            resp = client.post("/api/ai/generate-description", json={
                "imovel_data": {
                    "tipo_imovel": "terreno",
                },
            })
            assert resp.status_code == 400


class TestLeadScore:
    def test_score_with_cliente_id(self, client):
        client._mock_supabase.set_table_data("clientes", {
            "id": "c1",
            "nome": "Joao Silva",
            "email": "joao@test.com",
            "telefone": "11999999999",
            "origem": "indicacao",
            "interesse": "Apartamento 3 quartos",
            "valor_estimado": 500000,
            "etapa_atual": "visitas",
            "probabilidade": 70,
        })
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            return_value={
                "score": 78,
                "justificativa": "Lead com dados completos e alta probabilidade.",
                "recomendacao": "Agendar visita ao imovel.",
            },
        ):
            resp = client.post("/api/ai/lead-score", json={
                "cliente_id": "c1",
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["score"] == 78
            assert "justificativa" in data

    def test_score_with_cliente_data(self, client):
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            return_value={
                "score": 55,
                "justificativa": "Dados parciais.",
                "recomendacao": "Completar cadastro.",
            },
        ):
            resp = client.post("/api/ai/lead-score", json={
                "cliente_data": {
                    "nome": "Maria",
                    "email": "maria@test.com",
                    "interesse": "Casa",
                },
            })
            assert resp.status_code == 200

    def test_score_no_data(self, client):
        resp = client.post("/api/ai/lead-score", json={})
        assert resp.status_code == 400

    def test_score_cliente_not_found(self, client):
        client._mock_supabase.set_table_data("clientes", None)
        resp = client.post("/api/ai/lead-score", json={
            "cliente_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_score_ai_error(self, client):
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            side_effect=Exception("AI service down"),
        ):
            resp = client.post("/api/ai/lead-score", json={
                "cliente_data": {
                    "nome": "Test",
                },
            })
            assert resp.status_code == 500

    def test_score_ai_value_error(self, client):
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            side_effect=ValueError("API key not configured"),
        ):
            resp = client.post("/api/ai/lead-score", json={
                "cliente_data": {"nome": "Test"},
            })
            assert resp.status_code == 400


class TestSuggestPrice:
    def test_suggest_with_imovel_id(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "tipo_imovel": "apartamento",
            "cidade": "Sao Paulo",
            "bairro": "Jardins",
            "area_privativa": 120,
            "quartos": 3,
            "vagas": 2,
            "natureza": "imovel",
            "status": "ativo",
        })
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            return_value={
                "preco_sugerido": 850000,
                "faixa_min": 750000,
                "faixa_max": 950000,
                "analise": "Baseado em comparaveis da regiao.",
            },
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_id": "a1",
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["preco_sugerido"] == 850000
            assert data["faixa_min"] == 750000
            assert data["faixa_max"] == 950000
            assert "analise" in data
            assert "total_comparaveis" in data

    def test_suggest_with_imovel_data(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            return_value={
                "preco_sugerido": 600000,
                "faixa_min": 500000,
                "faixa_max": 700000,
                "analise": "Estimativa sem comparaveis.",
            },
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_data": {
                    "tipo_imovel": "casa",
                    "cidade": "Campinas",
                    "bairro": "Cambui",
                    "area_privativa": 200,
                    "quartos": 4,
                },
            })
            assert resp.status_code == 200

    def test_suggest_no_data(self, client):
        resp = client.post("/api/ai/suggest-price", json={})
        assert resp.status_code == 400

    def test_suggest_imovel_not_found(self, client):
        client._mock_supabase.set_table_data("ativos", None)
        resp = client.post("/api/ai/suggest-price", json={
            "imovel_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_suggest_ai_error(self, client):
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            side_effect=Exception("OpenAI timeout"),
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_data": {
                    "tipo_imovel": "apartamento",
                    "quartos": 2,
                },
            })
            assert resp.status_code == 500

    def test_suggest_ai_value_error(self, client):
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            side_effect=ValueError("No API key"),
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_data": {"tipo_imovel": "casa"},
            })
            assert resp.status_code == 400

    def test_suggest_with_comparables(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "tipo_imovel": "apartamento",
            "cidade": "Sao Paulo",
            "bairro": "Vila Mariana",
            "area_privativa": 80,
            "quartos": 2,
            "vagas": 1,
            "natureza": "imovel",
            "status": "ativo",
        })
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            return_value={
                "preco_sugerido": 500000,
                "faixa_min": 450000,
                "faixa_max": 550000,
                "analise": "Baseado em 5 comparaveis.",
            },
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_id": "a1",
            })
            assert resp.status_code == 200
