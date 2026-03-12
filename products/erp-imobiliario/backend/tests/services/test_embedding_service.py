"""
Tests for the embedding service — build_ativo_text, generate_embedding, embed_ativo.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.embedding_service import (
    build_ativo_text,
    generate_embedding,
    embed_ativo,
    embed_ativos_batch,
)


# ========== BUILD ATIVO TEXT ==========

class TestBuildAtivoText:
    def test_build_ativo_text_imovel(self):
        ativo = {
            "natureza": "imovel",
            "tipo_imovel": "apartamento",
            "bairro": "Moema",
            "cidade": "São Paulo",
            "estado": "SP",
            "zona": "Zona Sul",
            "area_privativa": 120,
            "quartos": 3,
            "suites": 1,
            "vagas": 2,
            "valor": 850000,
            "titulo_anuncio": "Lindo apartamento em Moema",
            "descricao_seo": "Apartamento espaçoso com vista",
            "pontos_de_interesse": ["escola", "metrô"],
            "condominio_nome": "Edifício Aurora",
            "interesses_descricao": "Aceita casa na zona norte",
        }
        text = build_ativo_text(ativo)
        assert "apartamento" in text
        assert "Moema" in text
        assert "São Paulo" in text
        assert "120" in text
        assert "Quartos: 3" in text
        assert "Suítes: 1" in text
        assert "Vagas: 2" in text
        assert "850000" in text
        assert "Lindo apartamento" in text
        assert "espaçoso" in text
        assert "escola" in text
        assert "Aurora" in text
        assert "Aceita casa" in text

    def test_build_ativo_text_permuta_imovel(self):
        ativo = {
            "natureza": "permuta_imovel",
            "tipo_imovel": "casa",
            "cidade": "Campinas",
            "estado": "SP",
            "faixa_preco_min": 400000,
            "faixa_preco_max": 600000,
            "quartos_min": 3,
            "vagas_min": 2,
            "metragem_min": 100,
            "metragem_max": 200,
            "interesses_descricao": "Prefiro casa com quintal",
        }
        text = build_ativo_text(ativo)
        assert "casa" in text
        assert "Campinas" in text
        assert "400000" in text
        assert "600000" in text
        assert "Quartos mínimos: 3" in text
        assert "Vagas mínimas: 2" in text
        assert "100" in text
        assert "200" in text
        assert "quintal" in text

    def test_build_ativo_text_permuta_automovel(self):
        ativo = {
            "natureza": "permuta_automovel",
            "tipo_veiculo": "SUV",
            "marca": "Toyota",
            "modelo": "Corolla Cross",
            "motor": "2.0",
            "ano": 2023,
            "km": 15000,
            "valor": 180000,
            "interesses_descricao": "Aceita apartamento pequeno",
        }
        text = build_ativo_text(ativo)
        assert "SUV" in text
        assert "Toyota" in text
        assert "Corolla Cross" in text
        assert "2.0" in text
        assert "2023" in text
        assert "15000" in text
        assert "180000" in text
        assert "apartamento pequeno" in text

    def test_build_ativo_text_minimal_data(self):
        ativo = {"natureza": "imovel"}
        text = build_ativo_text(ativo)
        assert text == ""

    def test_build_ativo_text_empty_dict(self):
        text = build_ativo_text({})
        assert text == ""

    def test_build_ativo_text_unknown_natureza(self):
        ativo = {"natureza": "outro", "interesses_descricao": "algo"}
        text = build_ativo_text(ativo)
        assert "algo" in text

    def test_build_ativo_text_imovel_area_total_fallback(self):
        """Uses area_total when area_privativa is not available."""
        ativo = {"natureza": "imovel", "area_total": 200}
        text = build_ativo_text(ativo)
        assert "200" in text

    def test_build_ativo_text_pontos_de_interesse_string(self):
        """Handles non-list pontos_de_interesse."""
        ativo = {"natureza": "imovel", "pontos_de_interesse": "escola, parque"}
        text = build_ativo_text(ativo)
        assert "escola, parque" in text


# ========== GENERATE EMBEDDING ==========

class TestGenerateEmbedding:
    @pytest.mark.asyncio
    async def test_generate_embedding_success(self):
        mock_embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"embedding": mock_embedding}]
        }

        with patch("app.services.embedding_service.resolve_credential", return_value="test-key"), \
             patch("httpx.AsyncClient") as MockClient:

            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await generate_embedding("Test text")
            assert len(result) == 1536
            assert result == mock_embedding

            # Verify the API was called correctly
            mock_client_instance.post.assert_called_once()
            call_args = mock_client_instance.post.call_args
            assert call_args[0][0] == "https://api.openai.com/v1/embeddings"
            assert call_args[1]["json"]["model"] == "text-embedding-3-small"
            assert call_args[1]["json"]["input"] == "Test text"

    @pytest.mark.asyncio
    async def test_generate_embedding_no_api_key(self):
        with patch("app.services.embedding_service.resolve_credential", return_value=None):
            with pytest.raises(ValueError, match="Chave da API OpenAI"):
                await generate_embedding("Test text")

    @pytest.mark.asyncio
    async def test_generate_embedding_api_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("app.services.embedding_service.resolve_credential", return_value="test-key"), \
             patch("httpx.AsyncClient") as MockClient:

            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with pytest.raises(ValueError, match="Erro na API OpenAI Embeddings: 500"):
                await generate_embedding("Test text")


# ========== EMBED ATIVO ==========

class TestEmbedAtivo:
    @pytest.mark.asyncio
    async def test_embed_ativo_stores_embedding(self):
        ativo = {
            "id": "ativo-123",
            "natureza": "imovel",
            "tipo_imovel": "apartamento",
            "cidade": "São Paulo",
        }
        mock_embedding = [0.5] * 1536

        mock_db = MagicMock()
        mock_update_chain = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value = mock_update_chain
        mock_update_chain.update.return_value = mock_update_chain
        mock_update_chain.eq.return_value = mock_update_chain
        mock_update_chain.execute.return_value = MagicMock()

        with patch("app.services.embedding_service.generate_embedding", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_embedding

            result = await embed_ativo(ativo, mock_db)
            assert result is True
            mock_gen.assert_called_once()
            mock_db.table.assert_called_with("ativos")

    @pytest.mark.asyncio
    async def test_embed_ativo_empty_text(self):
        ativo = {"id": "ativo-123", "natureza": "imovel"}
        mock_db = MagicMock()

        result = await embed_ativo(ativo, mock_db)
        assert result is False

    @pytest.mark.asyncio
    async def test_embed_ativos_batch_success(self):
        mock_db = MagicMock()

        # Mock fetching ativo data
        ativo_data = {
            "id": "ativo-1",
            "natureza": "imovel",
            "tipo_imovel": "casa",
            "cidade": "Campinas",
        }
        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=ativo_data)
        mock_query.update.return_value = mock_query
        mock_db.table.return_value = mock_query

        with patch("app.services.embedding_service.generate_embedding", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = [0.1] * 1536

            result = await embed_ativos_batch(["ativo-1"], mock_db)
            assert result["total"] == 1
            assert result["embedded"] == 1
            assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_embed_ativos_batch_with_errors(self):
        mock_db = MagicMock()

        # Mock: first ativo found, second not found
        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.update.return_value = mock_query

        call_count = 0
        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(data={"id": "a1", "natureza": "imovel", "tipo_imovel": "casa", "cidade": "SP"})
            return MagicMock(data=None)

        mock_query.execute.side_effect = side_effect
        mock_db.table.return_value = mock_query

        with patch("app.services.embedding_service.generate_embedding", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = [0.1] * 1536
            result = await embed_ativos_batch(["a1", "a2"], mock_db)
            assert result["total"] == 2
            assert result["embedded"] == 1
            assert result["errors"] == 1
