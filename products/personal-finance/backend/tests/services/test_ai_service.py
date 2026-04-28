"""Unit tests for the Personal Finance AI service (Phase 7 P1 indicators)."""
import pytest
from unittest.mock import AsyncMock, patch


class TestCategorizeTransaction:

    @pytest.mark.asyncio
    async def test_parses_category_and_confidence(self):
        from app.services.ai_service import categorize_transaction
        canned = "CATEGORY: Alimentação\nCONFIDENCE: 0.93\nEXPLANATION: padaria recorrente em manhãs úteis"
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = canned
            out = await categorize_transaction(
                descricao="Padaria do Bairro",
                valor=18.50,
                tipo="despesa",
                comerciante="PADARIA DO BAIRRO LTDA",
                available_categories=[
                    {"id": "cat-1", "nome": "Alimentação", "tipo": "despesa"},
                    {"id": "cat-2", "nome": "Transporte", "tipo": "despesa"},
                ],
            )
        assert out["kind"] == "classification"
        assert out["label"] == "Alimentação"
        assert out["chip"] == "ALIMENTAÇÃO"
        assert out["confidence"] == 0.93
        assert out["matched_categoria_id"] == "cat-1"
        assert out["prompt_version"] == "pf-categorize@v1"

    @pytest.mark.asyncio
    async def test_unmatched_category_returns_no_id(self):
        from app.services.ai_service import categorize_transaction
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "CATEGORY: Lazer\nCONFIDENCE: 0.55\nEXPLANATION: x"
            out = await categorize_transaction(
                descricao="netflix",
                valor=39.90,
                tipo="despesa",
                available_categories=[{"id": "c1", "nome": "Alimentação"}],
            )
        assert out["label"] == "Lazer"
        assert out["matched_categoria_id"] is None

    @pytest.mark.asyncio
    async def test_empty_input_short_circuits(self):
        from app.services.ai_service import categorize_transaction
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            out = await categorize_transaction(descricao="", valor=10, tipo="despesa")
        assert out["label"] == "transação vazia"
        mock_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_unavailable_returns_empty(self):
        from app.services.ai_service import categorize_transaction
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM not configured")
            out = await categorize_transaction(descricao="x", valor=1, tipo="despesa")
        assert out["label"] == "indisponível"


class TestFlagRecurringExpense:

    @pytest.mark.asyncio
    async def test_parses_flag_probability_explanation(self):
        from app.services.ai_service import flag_recurring_expense
        canned = (
            "FLAG: recorrente\n"
            "PROBABILITY: 0.91\n"
            "EXPLANATION: três cobranças mensais consecutivas no mesmo valor"
        )
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = canned
            out = await flag_recurring_expense(
                descricao="NETFLIX BRASIL",
                valor=39.90,
                tipo="despesa",
                similar_history=[
                    {"data": "2026-03-15", "valor": 39.90, "descricao": "NETFLIX"},
                    {"data": "2026-02-15", "valor": 39.90, "descricao": "NETFLIX"},
                ],
            )
        assert out["kind"] == "flag"
        assert out["label"] == "recorrente"
        assert out["chip"] == "RECORRENTE"
        assert out["score"] == 0.91
        assert out["prompt_version"] == "pf-recurring@v1"

    @pytest.mark.asyncio
    async def test_pontual_flag_chip(self):
        from app.services.ai_service import flag_recurring_expense
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "FLAG: pontual\nPROBABILITY: 0.18\nEXPLANATION: única ocorrência"
            out = await flag_recurring_expense(descricao="x", valor=1, tipo="despesa")
        assert out["label"] == "pontual"
        assert out["chip"] == "PONTUAL"

    @pytest.mark.asyncio
    async def test_empty_descricao_short_circuits(self):
        from app.services.ai_service import flag_recurring_expense
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            out = await flag_recurring_expense(descricao="", valor=1, tipo="despesa")
        assert out["label"] == "transação sem descrição"
        mock_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_probability_clamps_to_unit_interval(self):
        from app.services.ai_service import flag_recurring_expense
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "FLAG: recorrente\nPROBABILITY: 9.99\nEXPLANATION: x"
            out = await flag_recurring_expense(descricao="x", valor=1, tipo="despesa")
        assert out["score"] == 1.0

    @pytest.mark.asyncio
    async def test_llm_unavailable_returns_empty(self):
        from app.services.ai_service import flag_recurring_expense
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM not configured")
            out = await flag_recurring_expense(descricao="x", valor=1, tipo="despesa")
        assert out["label"] == "indisponível"
