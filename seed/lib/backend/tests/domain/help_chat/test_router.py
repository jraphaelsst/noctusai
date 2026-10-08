"""`create_help_chat_router` — auth boundary, validation, SSE framing, and
error mapping. The model call is the seed `FakeProvider` behind the
router's `stream_fn` seam (see `conftest.FakeStream`), so assertions are
about what the router SENDS and how it maps failures — never about a
model's prose.
"""
from __future__ import annotations

import json

import pytest
from noctusai_lib.domain.help_chat import FakeHelpChatStore, HelpChatKnowledgeMissing, HelpChatRateLimiter
from noctusai_lib.integrations.llm import LLMAPIError, LLMBudgetExceeded, LLMNotConfigured

from tests.domain.help_chat.conftest import AUTH_HEADER, FakeStream, ORG_ID, build_harness


def _sse_events(text: str) -> list[dict]:
    """Parse `data: {...}\\n\\n` frames back into dicts, in order."""
    events = []
    for line in text.split("\n\n"):
        line = line.strip()
        if not line:
            continue
        assert line.startswith("data: "), f"unexpected SSE line: {line!r}"
        events.append(json.loads(line[len("data: "):]))
    return events


class TestAuth:
    def test_requires_auth_strict_401(self, harness):
        resp = harness.client.post("/api/ajuda/chat", json={"messages": [{"role": "user", "content": "oi"}]})
        assert resp.status_code == 401


class TestValidation:
    def test_empty_messages_is_422(self, harness):
        resp = harness.client.post(
            "/api/ajuda/chat", json={"messages": []}, headers=AUTH_HEADER,
        )
        assert resp.status_code == 422

    def test_unknown_body_field_is_422_strict_http_model(self, harness):
        resp = harness.client.post(
            "/api/ajuda/chat",
            json={"messages": [{"role": "user", "content": "oi"}], "campo_desconhecido": True},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422

    def test_unknown_role_is_422(self, harness):
        resp = harness.client.post(
            "/api/ajuda/chat",
            json={"messages": [{"role": "system", "content": "oi"}]},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422

    def test_last_message_must_be_from_user(self, harness):
        resp = harness.client.post(
            "/api/ajuda/chat",
            json={"messages": [{"role": "assistant", "content": "oi"}]},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "ultima_mensagem_invalida"

    def test_too_many_turns_is_422(self, tmp_path):
        harness = build_harness(tmp_path, max_turns=2)
        resp = harness.client.post(
            "/api/ajuda/chat",
            json={"messages": [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"},
            ]},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "limite_de_turnos"

    def test_message_too_long_is_422(self, tmp_path):
        harness = build_harness(tmp_path, max_chars_per_message=10)
        resp = harness.client.post(
            "/api/ajuda/chat",
            json={"messages": [{"role": "user", "content": "x" * 11}]},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "mensagem_muito_longa"


class TestStreaming:
    def test_streams_deltas_then_done(self, harness):
        resp = harness.client.post(
            "/api/ajuda/chat",
            json={"messages": [{"role": "user", "content": "Como crio um negócio?"}], "pagina_atual": "/negocios"},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(resp.text)
        assert events == [{"delta": "Olá!"}, {"delta": " Como posso ajudar?"}, {"done": True}]

    def test_sends_system_prompt_with_product_knowledge_and_anthropic_cache_control(self, harness):
        harness.client.post(
            "/api/ajuda/chat",
            json={"messages": [{"role": "user", "content": "oi"}]},
            headers=AUTH_HEADER,
        )
        [call] = harness.stream.calls
        system = call["messages"][0]
        assert system["role"] == "system"
        assert "IgIg" in system["content"]
        assert "Novo negócio" in system["content"], "the product knowledge file content must be present"
        assert system["cache_control"] == {"type": "ephemeral"}, "prompt caching block must be present"
        assert call["provider"] == "anthropic"
        assert call["model"] == "claude-haiku-4-5"
        assert call["org_id"] == ORG_ID

    def test_preserves_multi_turn_history_order(self, harness):
        harness.client.post(
            "/api/ajuda/chat",
            json={"messages": [
                {"role": "user", "content": "primeira pergunta"},
                {"role": "assistant", "content": "primeira resposta"},
                {"role": "user", "content": "segunda pergunta"},
            ]},
            headers=AUTH_HEADER,
        )
        [call] = harness.stream.calls
        roles_and_content = [(m["role"], m.get("content")) for m in call["messages"]]
        assert roles_and_content == [
            ("system", roles_and_content[0][1]),
            ("user", "primeira pergunta"),
            ("assistant", "primeira resposta"),
            ("user", "segunda pergunta"),
        ]

    def test_never_logs_message_text(self, harness, caplog):
        import logging
        caplog.set_level(logging.INFO)
        harness.client.post(
            "/api/ajuda/chat",
            json={"messages": [{"role": "user", "content": "SEGREDO-NAO-DEVE-APARECER-NO-LOG"}]},
            headers=AUTH_HEADER,
        )
        for record in caplog.records:
            assert "SEGREDO-NAO-DEVE-APARECER-NO-LOG" not in record.getMessage()


class TestLongAnswers:
    """A reply cut off at the per-round token cap is continued, never
    presented as complete (2026-10-01: a 1200-token cap cut an IgIg
    walkthrough mid-section and the router still sent `done`)."""

    PERGUNTA = {"messages": [{"role": "user", "content": "Como monto e envio um orçamento?"}]}

    def _post(self, harness):
        resp = harness.client.post("/api/ajuda/chat", json=self.PERGUNTA, headers=AUTH_HEADER)
        assert resp.status_code == 200
        return _sse_events(resp.text)

    def test_truncated_round_is_continued_seamlessly(self, tmp_path):
        stream = FakeStream(chunks=(("Passo 1.", " Passo 2"), (" e passo 3.",)), truncated=(True, False))
        harness = build_harness(tmp_path, stream=stream)

        events = self._post(harness)

        assert events == [
            {"delta": "Passo 1."}, {"delta": " Passo 2"}, {"delta": " e passo 3."}, {"done": True},
        ], "the continuation streams as plain deltas, with no truncated frame"
        first, second = harness.stream.calls
        assert len(first["messages"]) == 2  # system + the user's question
        replay = [(m["role"], m.get("content")) for m in second["messages"][1:]]
        assert replay[0] == ("user", "Como monto e envio um orçamento?")
        assert replay[1] == ("assistant", "Passo 1. Passo 2"), "the partial reply is replayed verbatim"
        assert replay[2][0] == "user" and "Continue exatamente" in replay[2][1]

    def test_still_truncated_after_last_round_emits_truncated_before_done(self, tmp_path):
        stream = FakeStream(chunks=(("a",), ("b",), ("c",)), truncated=(True, True, True))
        harness = build_harness(tmp_path, stream=stream, max_continuations=2)

        events = self._post(harness)

        assert events == [{"delta": "a"}, {"delta": "b"}, {"delta": "c"}, {"truncated": True}, {"done": True}]
        assert len(harness.stream.calls) == 3, "1 round + max_continuations, never more"

    def test_continuation_disabled_reports_truncation_immediately(self, tmp_path):
        stream = FakeStream(chunks=(("a",),), truncated=(True,))
        harness = build_harness(tmp_path, stream=stream, max_continuations=0)

        assert self._post(harness) == [{"delta": "a"}, {"truncated": True}, {"done": True}]
        assert len(harness.stream.calls) == 1

    def test_complete_answer_makes_one_call(self, harness):
        assert self._post(harness)[-1] == {"done": True}
        assert len(harness.stream.calls) == 1

    def test_default_stream_fn_caps_each_round_at_4096_and_requests_outcome(self):
        """The production seam asks the provider for its stop signal — without
        `outcome`, truncation is undetectable and continuation never fires."""
        from noctusai_lib.domain.help_chat import router as help_chat_router

        assert help_chat_router.MAX_TOKENS_POR_RODADA == 4096
        import inspect

        assert "outcome" in inspect.signature(help_chat_router._default_stream_fn).parameters


class TestErrorMapping:
    def test_llm_not_configured_before_first_chunk_is_503(self, tmp_path):
        harness = build_harness(tmp_path, stream=FakeStream(erro=LLMNotConfigured("anthropic")))
        resp = harness.client.post(
            "/api/ajuda/chat", json={"messages": [{"role": "user", "content": "oi"}]}, headers=AUTH_HEADER,
        )
        assert resp.status_code == 503
        assert resp.json()["code"] == "ia_nao_configurada"

    def test_llm_budget_exceeded_before_first_chunk_is_429(self, tmp_path):
        harness = build_harness(
            tmp_path,
            stream=FakeStream(erro=LLMBudgetExceeded(org_id=ORG_ID, spent_brl=100.0, budget_brl=100.0)),
        )
        resp = harness.client.post(
            "/api/ajuda/chat", json={"messages": [{"role": "user", "content": "oi"}]}, headers=AUTH_HEADER,
        )
        assert resp.status_code == 429
        assert resp.json()["code"] == "orcamento_ia_excedido"

    def test_llm_api_error_before_first_chunk_is_502(self, tmp_path):
        harness = build_harness(tmp_path, stream=FakeStream(erro=LLMAPIError("anthropic", "timeout")))
        resp = harness.client.post(
            "/api/ajuda/chat", json={"messages": [{"role": "user", "content": "oi"}]}, headers=AUTH_HEADER,
        )
        assert resp.status_code == 502
        assert resp.json()["code"] == "ia_indisponivel"


class TestRateLimit:
    def test_returns_429_limite_de_mensagens_when_over_budget(self, tmp_path):
        limiter = HelpChatRateLimiter(max_requests=1, window_seconds=60.0)
        harness = build_harness(tmp_path, rate_limiter=limiter)
        first = harness.client.post(
            "/api/ajuda/chat", json={"messages": [{"role": "user", "content": "oi"}]}, headers=AUTH_HEADER,
        )
        assert first.status_code == 200
        second = harness.client.post(
            "/api/ajuda/chat", json={"messages": [{"role": "user", "content": "de novo"}]}, headers=AUTH_HEADER,
        )
        assert second.status_code == 429
        assert second.json()["code"] == "limite_de_mensagens"


class TestKnowledgeMustLoadAtMount:
    def test_missing_knowledge_file_raises_at_mount(self, tmp_path):
        from noctusai_lib.domain.help_chat import create_help_chat_router

        with pytest.raises(HelpChatKnowledgeMissing):
            create_help_chat_router(
                product_name="IgIg",
                product_slug="igig",
                store=FakeHelpChatStore(),
                knowledge_path=tmp_path / "does-not-exist.md",
                auth_dependency=lambda: None,
                org_id_from_auth=lambda auth: "x",
            )

    def test_empty_knowledge_file_raises_at_mount(self, tmp_path):
        from noctusai_lib.domain.help_chat import create_help_chat_router

        empty = tmp_path / "empty.md"
        empty.write_text("   \n", encoding="utf-8")
        with pytest.raises(HelpChatKnowledgeMissing):
            create_help_chat_router(
                product_name="IgIg",
                product_slug="igig",
                store=FakeHelpChatStore(),
                knowledge_path=empty,
                auth_dependency=lambda: None,
                org_id_from_auth=lambda auth: "x",
            )
