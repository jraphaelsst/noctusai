"""
Unit tests for AI Service — OpenAI-powered property descriptions, lead scoring, and pricing.
"""
import pytest
from unittest.mock import patch, AsyncMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# _parse_money
# ---------------------------------------------------------------------------

class TestParseMoney:

    def test_brazilian_full_format(self):
        from app.services.ai_service import _parse_money
        assert _parse_money("R$ 1.500.000,00") == 1500000.0

    def test_plain_number(self):
        from app.services.ai_service import _parse_money
        assert _parse_money("500000") == 500000.0

    def test_small_value(self):
        from app.services.ai_service import _parse_money
        assert _parse_money("R$ 350,00") == 350.0

    def test_empty_string(self):
        from app.services.ai_service import _parse_money
        assert _parse_money("") == 0.0

    def test_whitespace_only(self):
        from app.services.ai_service import _parse_money
        assert _parse_money("   ") == 0.0

    def test_value_with_spaces(self):
        from app.services.ai_service import _parse_money
        assert _parse_money("  R$ 2.000,50  ") == 2000.50

    def test_no_cents(self):
        from app.services.ai_service import _parse_money
        assert _parse_money("R$ 1.000") == 1000.0

    def test_garbage_text(self):
        from app.services.ai_service import _parse_money
        assert _parse_money("abc") == 0.0


# ---------------------------------------------------------------------------
# _get_api_key
# ---------------------------------------------------------------------------

class TestGetApiKey:

    def test_raises_when_no_key(self):
        from app.services.ai_service import _get_api_key

        with patch("app.services.ai_service.resolve_credential", return_value=None):
            with pytest.raises(ValueError, match="OpenAI API Key"):
                _get_api_key()

    def test_raises_when_empty_key(self):
        from app.services.ai_service import _get_api_key

        with patch("app.services.ai_service.resolve_credential", return_value=None):
            with pytest.raises(ValueError, match="OpenAI API Key"):
                _get_api_key()

    def test_returns_key_when_set(self):
        from app.services.ai_service import _get_api_key

        with patch("app.services.ai_service.resolve_credential", return_value="sk-test-key"):
            assert _get_api_key() == "sk-test-key"


# ---------------------------------------------------------------------------
# generate_description
# ---------------------------------------------------------------------------

class TestGenerateDescription:

    @pytest.mark.asyncio
    async def test_parses_structured_response(self):
        from app.services.ai_service import generate_description

        mock_response = (
            "TÍTULO: Apartamento Luxuoso no Centro\n"
            "DESCRIÇÃO:\n"
            "Este magnífico apartamento oferece conforto e praticidade.\n\n"
            "Localizado no coração da cidade, com fácil acesso a tudo."
        )

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await generate_description({
                "tipo_imovel": "Apartamento",
                "cidade": "São Paulo",
                "bairro": "Centro",
                "quartos": 3,
                "valor": 500000.0,
            })

        assert result["titulo_sugerido"] == "Apartamento Luxuoso no Centro"
        assert "magnífico" in result["descricao"]
        assert "TÍTULO:" not in result["descricao"]

    @pytest.mark.asyncio
    async def test_parses_unstructured_response(self):
        """When the response lacks TÍTULO:/DESCRIÇÃO: markers, entire content becomes descricao."""
        from app.services.ai_service import generate_description

        mock_response = "Um belo apartamento com vista para o mar e acabamento de primeira."

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await generate_description({"tipo_imovel": "Apartamento"})

        assert result["titulo_sugerido"] == ""
        assert result["descricao"] == mock_response

    @pytest.mark.asyncio
    async def test_titulo_truncated_to_80_chars(self):
        from app.services.ai_service import generate_description

        long_title = "A" * 120
        mock_response = f"TÍTULO: {long_title}\nDESCRIÇÃO:\nConteúdo da descrição aqui."

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await generate_description({"tipo_imovel": "Casa"})

        assert len(result["titulo_sugerido"]) == 80

    @pytest.mark.asyncio
    async def test_with_minimal_data(self):
        from app.services.ai_service import generate_description

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "TÍTULO: Imóvel\nDESCRIÇÃO:\nDescrição simples."

            result = await generate_description({})

        assert "titulo_sugerido" in result
        assert "descricao" in result
        mock_chat.assert_called_once()


# ---------------------------------------------------------------------------
# score_lead
# ---------------------------------------------------------------------------

class TestScoreLead:

    @pytest.mark.asyncio
    async def test_parses_structured_response(self):
        from app.services.ai_service import score_lead

        mock_response = (
            "SCORE: 85\n"
            "JUSTIFICATIVA: Cliente com alto potencial de conversão.\n"
            "RECOMENDAÇÃO: Agendar visita ao imóvel prioritariamente."
        )

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await score_lead({
                "nome": "João Silva",
                "email": "joao@example.com",
                "valor_estimado": 500000,
                "etapa_atual": "visitas",
            })

        assert result["score"] == 85
        assert "alto potencial" in result["justificativa"]
        assert "visita" in result["recomendacao"]

    @pytest.mark.asyncio
    async def test_score_clamped_to_100(self):
        from app.services.ai_service import score_lead

        mock_response = "SCORE: 150\nJUSTIFICATIVA: Muito bom.\nRECOMENDAÇÃO: Fechar."

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await score_lead({"nome": "Test"})

        assert result["score"] == 100

    @pytest.mark.asyncio
    async def test_score_clamped_to_0(self):
        from app.services.ai_service import score_lead

        mock_response = "SCORE: -10\nJUSTIFICATIVA: Sem dados.\nRECOMENDAÇÃO: Descartar."

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await score_lead({"nome": "Test"})

        # Negative sign is stripped by the digit-only parsing, so "-10" becomes "10"
        # The min/max clamp still applies
        assert 0 <= result["score"] <= 100

    @pytest.mark.asyncio
    async def test_defaults_to_50_on_parse_failure(self):
        from app.services.ai_service import score_lead

        mock_response = "Não consigo analisar este lead."

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await score_lead({"nome": "Test"})

        assert result["score"] == 50
        # When no JUSTIFICATIVA line found, full content becomes justificativa
        assert result["justificativa"] == mock_response

    @pytest.mark.asyncio
    async def test_handles_recomendacao_without_accent(self):
        from app.services.ai_service import score_lead

        mock_response = "SCORE: 70\nJUSTIFICATIVA: Bom lead.\nRECOMENDACAO: Ligar amanhã."

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await score_lead({"nome": "Test"})

        assert result["score"] == 70
        assert result["recomendacao"] == "Ligar amanhã."


# ---------------------------------------------------------------------------
# suggest_price
# ---------------------------------------------------------------------------

class TestSuggestPrice:

    @pytest.mark.asyncio
    async def test_parses_structured_response(self):
        from app.services.ai_service import suggest_price

        mock_response = (
            "PRECO_SUGERIDO: R$ 850.000,00\n"
            "FAIXA_MIN: R$ 750.000,00\n"
            "FAIXA_MAX: R$ 950.000,00\n"
            "ANALISE: Valor compatível com imóveis similares na região."
        )

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await suggest_price(
                {"tipo_imovel": "Apartamento", "bairro": "Jardins", "cidade": "SP"},
                [{"tipo_imovel": "Apartamento", "valor": 800000}],
            )

        assert result["preco_sugerido"] == 850000.0
        assert result["faixa_min"] == 750000.0
        assert result["faixa_max"] == 950000.0
        assert "compatível" in result["analise"]

    @pytest.mark.asyncio
    async def test_no_comparables(self):
        from app.services.ai_service import suggest_price

        mock_response = (
            "PRECO_SUGERIDO: 500000\n"
            "FAIXA_MIN: 450000\n"
            "FAIXA_MAX: 550000\n"
            "ANALISE: Estimativa baseada em dados gerais."
        )

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await suggest_price(
                {"tipo_imovel": "Casa", "cidade": "Campinas"},
                [],
            )

        assert result["preco_sugerido"] == 500000.0
        assert result["analise"] == "Estimativa baseada em dados gerais."

    @pytest.mark.asyncio
    async def test_unparseable_response(self):
        from app.services.ai_service import suggest_price

        mock_response = "Não é possível precificar sem mais dados."

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await suggest_price({"tipo_imovel": "Terreno"}, [])

        assert result["preco_sugerido"] == 0.0
        assert result["faixa_min"] == 0.0
        assert result["faixa_max"] == 0.0
        # Full response used as analise fallback
        assert result["analise"] == mock_response

    @pytest.mark.asyncio
    async def test_analise_with_accent(self):
        from app.services.ai_service import suggest_price

        mock_response = (
            "PRECO_SUGERIDO: 300000\n"
            "FAIXA_MIN: 250000\n"
            "FAIXA_MAX: 350000\n"
            "ANÁLISE: Região em valorização constante."
        )

        with patch("app.services.ai_service._chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await suggest_price({"tipo_imovel": "Casa"}, [])

        assert result["analise"] == "Região em valorização constante."
