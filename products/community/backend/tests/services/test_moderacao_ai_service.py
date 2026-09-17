"""Tests for `moderacao_ai_service.avaliar_mensagem` — contract §3
"AI-flag hand-off". `chat_completion` is the seed's LLM-provider
boundary (external SDK) — patching it is the allowed external-boundary
case, not a self-patch of this product's own code.
"""
import asyncio
from unittest.mock import patch
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.services.moderacao_ai_service import avaliar_mensagem

ORG = UUID("00000000-0000-0000-0000-000000000123")
MENSAGEM_ID = "11111111-1111-1111-1111-111111111111"


def _mensagem(**over) -> dict:
    base = {"id": MENSAGEM_ID, "conteudo": "texto qualquer da mensagem"}
    base.update(over)
    return base


def _client() -> MockSupabaseClient:
    mock = MockSupabaseClient()
    mock.set_table_data("mensagem_flags", [])
    return mock


class TestAvaliarMensagem:
    def test_no_conteudo_returns_none_without_calling_llm(self):
        client = _client()
        with patch("app.services.moderacao_ai_service.chat_completion") as mocked:
            result = asyncio.run(avaliar_mensagem(client, org_id=ORG, mensagem=_mensagem(conteudo=None)))
        assert result is None
        mocked.assert_not_called()

    def test_not_flagged_returns_none_and_inserts_nothing(self):
        client = _client()
        with patch(
            "app.services.moderacao_ai_service.chat_completion",
            return_value='{"flagged": false}',
        ):
            result = asyncio.run(avaliar_mensagem(client, org_id=ORG, mensagem=_mensagem()))
        assert result is None
        assert client.table("mensagem_flags").select("*").execute().data == []

    def test_flagged_inserts_row(self):
        client = _client()
        with patch(
            "app.services.moderacao_ai_service.chat_completion",
            return_value=(
                '{"flagged": true, "categoria": "spam", "severidade": "alta", '
                '"justificativa": "propaganda nao autorizada"}'
            ),
        ):
            result = asyncio.run(avaliar_mensagem(client, org_id=ORG, mensagem=_mensagem()))
        assert result is not None
        assert result["categoria"] == "spam"
        assert result["severidade"] == "alta"
        assert result["estado"] == "aberta"
        rows = client.table("mensagem_flags").select("*").execute().data
        assert len(rows) == 1

    def test_invalid_severidade_defaults_to_baixa(self):
        client = _client()
        with patch(
            "app.services.moderacao_ai_service.chat_completion",
            return_value='{"flagged": true, "severidade": "nao-existe"}',
        ):
            result = asyncio.run(avaliar_mensagem(client, org_id=ORG, mensagem=_mensagem()))
        assert result["severidade"] == "baixa"

    def test_malformed_json_returns_none(self):
        client = _client()
        with patch(
            "app.services.moderacao_ai_service.chat_completion",
            return_value="isto nao e json",
        ):
            result = asyncio.run(avaliar_mensagem(client, org_id=ORG, mensagem=_mensagem()))
        assert result is None

    def test_llm_failure_returns_none_never_raises(self):
        client = _client()
        with patch(
            "app.services.moderacao_ai_service.chat_completion",
            side_effect=RuntimeError("provider indisponível"),
        ):
            result = asyncio.run(avaliar_mensagem(client, org_id=ORG, mensagem=_mensagem()))
        assert result is None
