"""Conversation storage, end-of-attendance marker, rating route, and the
Supabase Real store (over `MockSupabaseClient`, schema-validated against the
core migration that creates the tables)."""
from __future__ import annotations

import json
import logging
from uuid import uuid4

import pytest
from noctusai_lib.domain.help_chat import (
    MARCADOR_CONCLUSAO,
    FakeHelpChatStore,
    HelpChatConversaAlheia,
    HelpChatStoreError,
    MarcadorFilter,
    make_help_chat_store,
)
from noctusai_lib.integrations.llm import LLMAPIError
from noctusai_lib.testing.mocks import MockSupabaseClient

from tests.domain.help_chat.conftest import AUTH_HEADER, FakeStream, ORG_ID, USER_ID, build_harness
from tests.domain.help_chat.test_router import _sse_events

MSG = {"role": "user", "content": "como cadastro um cliente?"}


def _chat(h, conversa_id=None, **extra):
    body = {"messages": [MSG], **extra}
    if conversa_id:
        body["conversa_id"] = conversa_id
    return h.client.post("/api/ajuda/chat", json=body, headers=AUTH_HEADER)


class TestMarcadorFilter:
    def test_strips_marker_inside_one_chunk(self):
        f = MarcadorFilter()
        out = f.feed(f"Por nada!\n{MARCADOR_CONCLUSAO}") + f.flush()
        assert out == "Por nada!\n"
        assert f.encontrado and f.texto_final() == "Por nada!"

    @pytest.mark.parametrize("corte", range(1, len(MARCADOR_CONCLUSAO)))
    def test_strips_marker_split_at_every_boundary(self, corte):
        texto = f"Por nada! {MARCADOR_CONCLUSAO}"
        i = len("Por nada! ") + corte
        f = MarcadorFilter()
        out = f.feed(texto[:i]) + f.feed(texto[i:]) + f.flush()
        assert MARCADOR_CONCLUSAO not in out and "[[" not in out
        assert f.encontrado
        assert f.texto_final() == "Por nada!"

    def test_marker_fed_char_by_char(self):
        f = MarcadorFilter()
        out = "".join(f.feed(c) for c in f"ok {MARCADOR_CONCLUSAO}") + f.flush()
        assert out == "ok " and f.encontrado

    def test_false_start_is_released_not_swallowed(self):
        f = MarcadorFilter()
        out = f.feed("veja [[Nota") + f.feed(" de rodapé]]") + f.flush()
        assert out == "veja [[Nota de rodapé]]" and not f.encontrado

    def test_dangling_prefix_flushes_as_text(self):
        f = MarcadorFilter()
        out = f.feed("fim [[ATEN") + f.flush()
        assert out == "fim [[ATEN" and not f.encontrado


class TestStorage:
    def test_stores_user_turn_and_assistant_reply_without_marker(self, tmp_path):
        cid = str(uuid4())
        h = build_harness(tmp_path, stream=FakeStream(chunks=(("Por nada!", " [[ATENDIMENTO_", "CONCLUIDO]]"),)))
        resp = _chat(h, cid, pagina_atual="/clientes")
        events = _sse_events(resp.text)
        assert "".join(e.get("delta", "") for e in events).rstrip() == "Por nada!"
        assert MARCADOR_CONCLUSAO not in resp.text
        assert events[-2:] == [{"encerrado": True}, {"done": True}]
        assert h.store.conversas[cid]["org_id"] == ORG_ID
        assert h.store.conversas[cid]["user_id"] == USER_ID
        assert h.store.conversas[cid]["produto"] == "igig"
        user, assistant = h.store.mensagens
        assert (user["papel"], user["conteudo"], user["pagina_atual"]) == ("user", MSG["content"], "/clientes")
        assert assistant["papel"] == "assistant" and assistant["conteudo"] == "Por nada!"
        assert assistant["parcial"] is False and assistant["modelo"] and assistant["latency_ms"] is not None

    def test_no_encerrado_without_marker(self, harness):
        events = _sse_events(_chat(harness, str(uuid4())).text)
        assert all("encerrado" not in e for e in events)
        assert events[-1] == {"done": True}

    def test_server_generates_conversa_id_when_absent(self, harness):
        assert _chat(harness).status_code == 200
        assert len(harness.store.conversas) == 1

    def test_invalid_conversa_id_is_422(self, harness):
        assert _chat(harness, "nao-e-uuid").status_code == 422

    def test_mid_stream_error_stores_partial_and_never_emits_encerrado(self, tmp_path):
        cid = str(uuid4())
        h = build_harness(tmp_path, stream=_FalhaNoMeio())
        events = _sse_events(_chat(h, cid).text)
        assert any("error" in e for e in events)
        assert all("encerrado" not in e and "done" not in e for e in events)
        assistant = h.store.mensagens[-1]
        assert assistant["papel"] == "assistant" and assistant["parcial"] is True
        assert assistant["conteudo"].startswith("Resposta")

    def test_store_failure_does_not_break_answer_and_logs_error(self, tmp_path, caplog):
        cid = str(uuid4())
        h = build_harness(tmp_path, store=FakeHelpChatStore(falhar=RuntimeError("db fora")))
        with caplog.at_level(logging.ERROR):
            resp = _chat(h, cid)
        events = _sse_events(resp.text)
        assert events[-1] == {"done": True} and any("delta" in e for e in events)
        erros = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert erros and all(cid in r.getMessage() and ORG_ID in r.getMessage() for r in erros)
        assert all(MSG["content"] not in r.getMessage() for r in caplog.records)

    def test_other_users_conversa_id_is_not_written_to(self, tmp_path, caplog):
        cid = str(uuid4())
        store = FakeHelpChatStore()
        store.registrar_turno_usuario(
            conversa_id=cid, produto="igig", org_id=ORG_ID, user_id=str(uuid4()),
            conteudo="privado", pagina_atual=None,
        )
        h = build_harness(tmp_path, store=store)
        with caplog.at_level(logging.ERROR):
            assert _chat(h, cid).status_code == 200
        assert [m["conteudo"] for m in store.mensagens] == ["privado"]
        assert any(cid in r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)


class _FalhaNoMeio(FakeStream):
    def __call__(self, messages, *, model, provider, org_id, outcome):
        async def gen():
            yield "Resposta [[ATENDIMENTO_CONCLUIDO]]"
            yield " cortada"
            raise LLMAPIError("boom")
        return gen()


class TestAvaliacao:
    def _stored(self, tmp_path):
        cid = str(uuid4())
        h = build_harness(tmp_path)
        _chat(h, cid)
        return h, cid

    def _post(self, h, body, headers=AUTH_HEADER):
        return h.client.post("/api/ajuda/avaliacao", json=body, headers=headers)

    def test_requires_auth_strict_401(self, harness):
        resp = harness.client.post(
            "/api/ajuda/avaliacao",
            json={"conversa_id": str(uuid4()), "nota": 5, "motivo": "concluido"},
        )
        assert resp.status_code == 401

    def test_204_and_last_rating_wins(self, tmp_path):
        h, cid = self._stored(tmp_path)
        r1 = self._post(h, {"conversa_id": cid, "nota": 2, "motivo": "inatividade"})
        r2 = self._post(h, {"conversa_id": cid, "nota": 5, "comentario": "ótimo", "motivo": "concluido"})
        assert (r1.status_code, r2.status_code) == (204, 204) and r2.content == b""
        c = h.store.conversas[cid]
        assert (c["nota"], c["comentario"], c["motivo_encerramento"]) == (5, "ótimo", "concluido")
        assert c["encerrada_em"] and c["avaliada_em"]

    def test_404_for_unknown_conversation_with_error_envelope(self, harness):
        resp = self._post(harness, {"conversa_id": str(uuid4()), "nota": 3, "motivo": "concluido"})
        assert resp.status_code == 404 and resp.json()["code"] == "conversa_nao_encontrada"

    def test_404_for_someone_elses_conversation(self, tmp_path):
        cid = str(uuid4())
        store = FakeHelpChatStore()
        store.registrar_turno_usuario(
            conversa_id=cid, produto="igig", org_id=ORG_ID, user_id=str(uuid4()),
            conteudo="x", pagina_atual=None,
        )
        h = build_harness(tmp_path, store=store)
        resp = self._post(h, {"conversa_id": cid, "nota": 1, "motivo": "concluido"})
        assert resp.status_code == 404 and store.conversas[cid]["nota"] is None

    @pytest.mark.parametrize("body", [
        {"nota": 5, "motivo": "concluido"},
        {"conversa_id": "x", "nota": 5, "motivo": "concluido"},
        {"conversa_id": str(uuid4()), "nota": 0, "motivo": "concluido"},
        {"conversa_id": str(uuid4()), "nota": 6, "motivo": "concluido"},
        {"conversa_id": str(uuid4()), "nota": 5, "motivo": "outro"},
        {"conversa_id": str(uuid4()), "nota": 5, "motivo": "concluido", "comentario": "a" * 1001},
        {"conversa_id": str(uuid4()), "nota": 5, "motivo": "concluido", "extra": 1},
    ])
    def test_invalid_body_is_422(self, harness, body):
        assert self._post(harness, body).status_code == 422

    def test_store_outage_is_503_logged_not_silent(self, tmp_path, caplog):
        h = build_harness(tmp_path, store=FakeHelpChatStore(falhar=HelpChatStoreError("x")))
        with caplog.at_level(logging.ERROR):
            resp = self._post(h, {"conversa_id": str(uuid4()), "nota": 4, "motivo": "concluido"})
        assert resp.status_code == 503 and resp.json()["code"] == "avaliacao_indisponivel"
        assert any(r.levelno >= logging.ERROR for r in caplog.records)


class TestSupabaseStore:
    def _store(self):
        client = MockSupabaseClient()
        return make_help_chat_store(client_fn=lambda: client), client

    def test_user_turn_creates_conversation_and_message(self):
        store, client = self._store()
        cid = str(uuid4())
        store.registrar_turno_usuario(
            conversa_id=cid, produto="igig", org_id=ORG_ID, user_id=USER_ID,
            conteudo="oi", pagina_atual="/x",
        )
        assert client.table("help_chat_conversas").upserted_payloads[0]["produto"] == "igig"
        assert client.table("help_chat_mensagens").inserted_payloads[0]["papel"] == "user"

    def test_reply_row_shape(self):
        store, client = self._store()
        store.registrar_resposta(
            conversa_id=str(uuid4()), conteudo="ok", modelo="m", latency_ms=5, truncated=False, parcial=True,
        )
        row = client.table("help_chat_mensagens").inserted_payloads[0]
        assert row["papel"] == "assistant" and row["parcial"] is True

    def test_rating_update_payload_and_false_when_no_row(self):
        store, client = self._store()
        client.set_table_data("help_chat_conversas", [])
        assert store.avaliar(
            conversa_id=str(uuid4()), org_id=ORG_ID, user_id=USER_ID, nota=5, comentario=None, motivo="concluido",
        ) is False
        payload = client.table("help_chat_conversas").updated_payloads[0]
        assert payload["nota"] == 5 and payload["motivo_encerramento"] == "concluido"

    def test_foreign_conversation_raises(self):
        store, client = self._store()
        cid = str(uuid4())
        client.set_table_data("help_chat_conversas", [
            {"id": cid, "produto": "igig", "org_id": ORG_ID, "user_id": str(uuid4())},
        ])
        with pytest.raises(HelpChatConversaAlheia):
            store.registrar_turno_usuario(
                conversa_id=cid, produto="igig", org_id=ORG_ID, user_id=USER_ID,
                conteudo="oi", pagina_atual=None,
            )
