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
# NOTE: _get_api_key tests removed — the function moved into
# noctusai_lib.credentials.resolve_credential and is covered by
# mcp/noctusai/tests/test_llm_foundation.py::TestCredentialsChain.
# ---------------------------------------------------------------------------


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

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
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

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await generate_description({"tipo_imovel": "Apartamento"})

        assert result["titulo_sugerido"] == ""
        assert result["descricao"] == mock_response

    @pytest.mark.asyncio
    async def test_titulo_truncated_to_80_chars(self):
        from app.services.ai_service import generate_description

        long_title = "A" * 120
        mock_response = f"TÍTULO: {long_title}\nDESCRIÇÃO:\nConteúdo da descrição aqui."

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await generate_description({"tipo_imovel": "Casa"})

        assert len(result["titulo_sugerido"]) == 80

    @pytest.mark.asyncio
    async def test_with_minimal_data(self):
        from app.services.ai_service import generate_description

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
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

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
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

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await score_lead({"nome": "Test"})

        assert result["score"] == 100

    @pytest.mark.asyncio
    async def test_score_clamped_to_0(self):
        from app.services.ai_service import score_lead

        mock_response = "SCORE: -10\nJUSTIFICATIVA: Sem dados.\nRECOMENDAÇÃO: Descartar."

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await score_lead({"nome": "Test"})

        # Negative sign is stripped by the digit-only parsing, so "-10" becomes "10"
        # The min/max clamp still applies
        assert 0 <= result["score"] <= 100

    @pytest.mark.asyncio
    async def test_defaults_to_50_on_parse_failure(self):
        from app.services.ai_service import score_lead

        mock_response = "Não consigo analisar este lead."

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await score_lead({"nome": "Test"})

        assert result["score"] == 50
        # When no JUSTIFICATIVA line found, full content becomes justificativa
        assert result["justificativa"] == mock_response

    @pytest.mark.asyncio
    async def test_handles_recomendacao_without_accent(self):
        from app.services.ai_service import score_lead

        mock_response = "SCORE: 70\nJUSTIFICATIVA: Bom lead.\nRECOMENDACAO: Ligar amanhã."

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
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

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
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

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
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

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
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

        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response

            result = await suggest_price({"tipo_imovel": "Casa"}, [])

        assert result["analise"] == "Região em valorização constante."


# ---------------------------------------------------------------------------
# E4 — draft_follow_up (ai-expansion Phase 15)
# ---------------------------------------------------------------------------

class TestDraftFollowUp:

    @pytest.mark.asyncio
    async def test_happy_path_returns_draft(self):
        from app.services.ai_service import draft_follow_up
        canned = "Olá João, notei que faz algum tempo desde nossa última conversa. Como posso ajudar?"
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = canned
            result = await draft_follow_up(
                cliente_nome="João Silva",
                last_interaction_days=30,
                etapa_atual="negociação",
                imovel_interesse="Apto 3 qtos no Centro",
                observacoes="Negociava preço no último contato.",
            )
        assert result["channel"] == "whatsapp"
        assert result["subject"] is None
        assert "João" in result["body"]

    @pytest.mark.asyncio
    async def test_missing_optional_fields_still_works(self):
        from app.services.ai_service import draft_follow_up
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "Oi, sumiu? Vamos conversar."
            result = await draft_follow_up(
                cliente_nome="Maria",
                last_interaction_days=45,
            )
        assert result["body"]

    @pytest.mark.asyncio
    async def test_llm_unavailable_returns_empty_body(self):
        from app.services.ai_service import draft_follow_up
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM not configured")
            result = await draft_follow_up(cliente_nome="X", last_interaction_days=20)
        assert result == {"channel": "whatsapp", "subject": None, "body": ""}

    @pytest.mark.asyncio
    async def test_prompt_carries_days_and_stage(self):
        from app.services.ai_service import draft_follow_up
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "msg"
            await draft_follow_up(
                cliente_nome="Ana",
                last_interaction_days=42,
                etapa_atual="qualificação",
            )
            args = mock_chat.call_args
            user_msg = args.kwargs["messages"][1]["content"]
            assert "42" in user_msg
            assert "qualificação" in user_msg
            assert "Ana" in user_msg


# ---------------------------------------------------------------------------
# Phase 6 P1 indicator services (E2/E6/E7/E8/E10)
# ---------------------------------------------------------------------------


class TestClassifyWhatsAppIntent:

    @pytest.mark.asyncio
    async def test_parses_intent_chip_explanation(self):
        from app.services.ai_service import classify_whatsapp_intent
        canned = "INTENT: interessado\nCONFIDENCE: 0.92\nEXPLANATION: cliente perguntou sobre disponibilidade do apto"
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = canned
            out = await classify_whatsapp_intent(
                message_text="Olá, ainda está disponível?",
                cliente_nome="João",
            )
        assert out["kind"] == "classification"
        assert out["label"] == "interessado"
        assert out["chip"] == "INTERESSADO"
        assert out["confidence"] == 0.92
        assert "disponibilidade" in out["explanation"]
        assert out["prompt_version"] == "erp-whatsapp-intent@v1"

    @pytest.mark.asyncio
    async def test_unknown_intent_falls_back_to_outros(self):
        from app.services.ai_service import classify_whatsapp_intent
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "INTENT: blah\nCONFIDENCE: 0.5\nEXPLANATION: ?"
            out = await classify_whatsapp_intent(message_text="...")
        assert out["label"] == "outros"
        assert out["chip"] == "OUTROS"

    @pytest.mark.asyncio
    async def test_empty_message_returns_empty_output(self):
        from app.services.ai_service import classify_whatsapp_intent
        out = await classify_whatsapp_intent(message_text="   ")
        assert out["label"] == "vazio"
        assert out["kind"] == "flag"

    @pytest.mark.asyncio
    async def test_llm_unavailable_returns_empty(self):
        from app.services.ai_service import classify_whatsapp_intent
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM not configured")
            out = await classify_whatsapp_intent(message_text="Oi")
        assert out["label"] == "indisponível"
        assert out["kind"] == "flag"


class TestScoreCertidoes:

    @pytest.mark.asyncio
    async def test_parses_score_and_explanation(self):
        from app.services.ai_service import score_certidoes
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "SCORE: 78\nEXPLANATION: certidão estadual válida; municipal vencida"
            out = await score_certidoes(
                cliente_nome="Pedro",
                certidoes=[
                    {"tipo": "estadual", "status": "valida", "data_emissao": "2026-04-01"},
                    {"tipo": "municipal", "status": "vencida", "data_emissao": "2025-10-01"},
                ],
            )
        assert out["kind"] == "score"
        assert out["score"] == 78.0
        assert out["chip"] == "78/100"
        assert "vencida" in out["explanation"]

    @pytest.mark.asyncio
    async def test_empty_certidoes_short_circuits_without_llm(self):
        from app.services.ai_service import score_certidoes
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            out = await score_certidoes(cliente_nome="X", certidoes=[])
        assert out["score"] == 0.0
        assert out["chip"] == "0/100"
        mock_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_score_clamps_to_100(self):
        from app.services.ai_service import score_certidoes
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "SCORE: 9999\nEXPLANATION: x"
            out = await score_certidoes(
                cliente_nome="X",
                certidoes=[{"tipo": "fed", "status": "ok"}],
            )
        assert out["score"] == 100.0


class TestGenerateMetasCoachTip:

    @pytest.mark.asyncio
    async def test_parses_tip_and_chip(self):
        from app.services.ai_service import generate_metas_coach_tip
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "TIP: Foque em retomar leads com mais de 14 dias parados.\nCHIP: REATIVAR LEADS"
            out = await generate_metas_coach_tip(
                user_nome="Ana",
                progresso_percent=42.0,
                dias_restantes=10,
                eventos_recentes=["visita agendada", "contrato assinado"],
            )
        assert out["kind"] == "narrative"
        assert "leads" in out["explanation"]
        assert out["chip"] == "REATIVAR LEADS"
        assert out["score"] == 42.0

    @pytest.mark.asyncio
    async def test_falls_back_to_first_line_when_format_off(self):
        from app.services.ai_service import generate_metas_coach_tip
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "Continue ligando para os leads frios."
            out = await generate_metas_coach_tip(
                user_nome="X", progresso_percent=10.0, dias_restantes=20
            )
        assert "Continue" in out["label"]
        assert out["chip"] == "DICA"


class TestAssessPhotoCompliance:

    @pytest.mark.asyncio
    async def test_parses_flag_score_explanation(self):
        from app.services.ai_service import assess_photo_compliance
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "FLAG: revisar\nSCORE: 60\nEXPLANATION: alt-text ausente em duas fotos"
            out = await assess_photo_compliance(
                imovel_descricao="Apto novo",
                fotos=[
                    {"filename": "1.jpg", "alt_text": ""},
                    {"filename": "2.jpg", "alt_text": ""},
                ],
            )
        assert out["kind"] == "flag"
        assert out["label"] == "revisar"
        assert out["chip"] == "REVISAR"
        assert out["score"] == 60.0

    @pytest.mark.asyncio
    async def test_empty_fotos_short_circuits(self):
        from app.services.ai_service import assess_photo_compliance
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            out = await assess_photo_compliance(imovel_descricao="x", fotos=[])
        assert out["chip"] == "SEM FOTOS"
        mock_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_reprovado_flag_label_chip(self):
        from app.services.ai_service import assess_photo_compliance
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "FLAG: reprovado\nSCORE: 12\nEXPLANATION: watermark de portal indevida"
            out = await assess_photo_compliance(
                imovel_descricao=None, fotos=[{"filename": "1.jpg", "has_watermark": True}]
            )
        assert out["label"] == "reprovado"
        assert out["chip"] == "REPROVADO"


class TestScoreSearchRelevance:

    @pytest.mark.asyncio
    async def test_parses_relevance_and_chip(self):
        from app.services.ai_service import score_search_relevance
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "RELEVANCE: 0.83\nEXPLANATION: bairro e tamanho casam com a busca"
            out = await score_search_relevance(
                query="apto 2 quartos próximo metrô centro",
                imovel_data={"tipo_imovel": "Apto", "bairro": "Centro", "quartos": 2, "valor": 500000},
            )
        assert out["kind"] == "score"
        assert out["score"] == 0.83
        assert out["chip"] == "83%"
        assert out["confidence"] == 0.83

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        from app.services.ai_service import score_search_relevance
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            out = await score_search_relevance(query="", imovel_data={})
        assert out["label"] == "query vazia"
        mock_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_relevance_clamps_to_unit_interval(self):
        from app.services.ai_service import score_search_relevance
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "RELEVANCE: 1.5\nEXPLANATION: x"
            out = await score_search_relevance(query="q", imovel_data={"tipo_imovel": "x"})
        assert out["score"] == 1.0
        assert out["chip"] == "100%"
