"""Guardrails B8.4 (agents half): once ``registrar_identificacao`` stores a CPF / RG, exactly that value is masked in
the thread's stored rows (the lead's text, the text extracted from its media), the failure of the masking is visible
and never reaches the lead, and the turn response says an identification was registered."""
from __future__ import annotations

import json
import logging
import re
from uuid import UUID

import pytest
from noctusai_lib.integrations.llm import FakeProvider
from noctusai_lib.primitives.identificador_redacao import redigir_estrutura, redigir_valores

from app.channels import turno as turno_mod
from tests.channels.conftest import turn_body
from tests.channels.test_julia_v2_e2e import (  # noqa: F401 -- ``mundo`` is the fixture
    CPF, RG, call, ctx_campanha, imovel, mundo, say, step,
)

CPF_DIGITOS = CPF.replace(".", "").replace("-", "")
OUTRO = "11987654321"  # a phone: 11 digits, NOT the registered value


def _ate_a_identificacao(chan, extra: list):
    """Turns 1-3 of the campaign scenario (profile, offers, a liked property + visit intent), then ``extra``."""
    chan.use_provider(FakeProvider(tool_responses=[
        step(call("abrir_skill", nome="qualificar-lead"), call("abrir_skill", nome="ofertar-imoveis")),
        step(call("registrar_perfil", itens=[
            {"criterio": "operacao", "valor": "compra", "trecho": "Quero comprar"},
            {"criterio": "interesse_campanha", "valor": "esse_e_similares", "trecho": "aceito ver parecidos"},
            {"criterio": "tipo_imovel", "valor": "apartamento", "trecho": "um apartamento"},
            {"criterio": "regioes", "valor": ["Pinheiros"], "trecho": "em Pinheiros"},
            {"criterio": "faixa_preco", "valor": {"max": 800000}, "trecho": "até 800 mil"},
            {"criterio": "prazo_decisao", "valor": "ate_3m", "trecho": "em até 3 meses"},
            {"criterio": "forma_pagamento", "valor": "financiamento", "trecho": "financiado"},
        ])),
        step(call("avaliar_lead")),
        step(call("oferecer_imoveis", modo="similares")),
        say("Separei 3 opções: https://imob.exemplo/B1 https://imob.exemplo/B2 https://imob.exemplo/B3."),
        step(call("registrar_reacao_imovel", codigo="B1", reacao="gostou"),
             call("registrar_intencao_visita", codigo="B1", preferencia_horario="sábado")),
        say("Ótimo! Qual seu nome completo, e-mail, CPF e RG?"),
        *extra,
    ]))
    from tests.channels.test_julia_v2_e2e import MENSAGEM_1
    chan.turn(turn_body(MENSAGEM_1, ids=["m1"], contexto=ctx_campanha()))
    chan.turn(turn_body("Gostei do B1, quero visitar", ids=["m2"], contexto=ctx_campanha()))


def _linhas(chan, resp: dict):
    return chan.rt.stores.messages.list(chan.org_id, UUID(resp["thread_id"]), limite=200)


def _blob(linhas) -> str:
    return json.dumps([[r.texto, r.blocks, r.meta] for r in linhas], default=str, ensure_ascii=False)


def _turno_identificacao(chan, *textos: str, midia: dict | None = None, ids=("m3",)):
    body = turn_body(*textos, ids=list(ids), contexto=ctx_campanha())
    if midia is not None:
        body["messages"][0]["midia"] = midia
    return chan.turn(body).json()


class TestPureRedaction:
    def test_plain_and_punctuated_cpf_and_rg(self):
        t = f"CPF {CPF} ou {CPF_DIGITOS}, RG {RG} / 123456789 e 12 345 678-9"
        out = redigir_valores(t, [CPF_DIGITOS, "123456789"])
        assert out == "CPF *** ou ***, RG *** / *** e ***"

    def test_only_the_registered_value_is_masked(self):
        out = redigir_valores(f"tel {OUTRO} cpf {CPF} cep 01310-100", [CPF_DIGITOS])
        assert OUTRO in out and "01310-100" in out and CPF not in out and out.count("***") == 1

    def test_idempotent_and_short_values_are_ignored(self):
        uma = redigir_valores(f"cpf {CPF}", [CPF_DIGITOS])
        assert redigir_valores(uma, [CPF_DIGITOS]) == uma
        assert redigir_valores("123", ["123"]) == "123"

    def test_rg_with_a_letter_is_case_insensitive(self):
        assert redigir_valores("rg 12.345.678-x", ["12345678X"]) == "rg ***"

    def test_every_string_of_a_structure(self):
        meta = {"midia": {"tipo": "documento", "texto_extraido": f"CPF: {CPF}", "n": 3}, "l": [CPF_DIGITOS, 1]}
        assert redigir_estrutura(meta, [CPF_DIGITOS]) == {
            "midia": {"tipo": "documento", "texto_extraido": "CPF: ***", "n": 3}, "l": ["***", 1]}


class TestTheTurnMasksTheStoredCopy:
    def test_text_and_extracted_media_text_are_masked_but_another_number_is_not(self, mundo):
        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_identificacao", campo="cpf", valor=CPF)),
            say("Anotado."),
        ])
        r = _turno_identificacao(
            chan, f"Meu CPF é {CPF}, o telefone é {OUTRO}",
            midia={"tipo": "documento", "texto_extraido": f"CPF {CPF_DIGITOS} Nome Maria", "legenda": f"cpf {CPF}"})
        assert r["identificacao_registrada"] is True
        blob = _blob(_linhas(chan, r))
        assert CPF not in blob and CPF_DIGITOS not in blob
        assert OUTRO in blob  # not the registered value
        [u] = [x for x in _linhas(chan, r) if x.role == "user" and "telefone" in x.texto]
        assert u.texto == f"Meu CPF é ***, o telefone é {OUTRO}"
        assert u.meta["midia"]["texto_extraido"] == "CPF *** Nome Maria" and u.meta["midia"]["legenda"] == "cpf ***"
        # the encrypted record is the only place the number survives
        rec = chan.ident._store.obter(chan.org_id, chan.lead_ref().id)
        assert chan.ident._cipher.decifrar(rec.cpf_cifrado) == CPF_DIGITOS

    def test_rg_is_masked_and_the_next_turn_runs_on_the_masked_history(self, mundo):
        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_identificacao", campo="rg", valor=RG)),
            say("Anotado."), say("Certo."),
        ])
        r = _turno_identificacao(chan, f"RG {RG}")
        assert r["identificacao_registrada"] is True
        assert "12.345.678-9" not in _blob(_linhas(chan, r))
        chan.turn(turn_body("ok", ids=["m4"], contexto=ctx_campanha()))
        historico = json.dumps([m.content for m in chan.provider.calls[-1]["messages"]], ensure_ascii=False)
        assert "12.345.678-9" not in historico and "123456789" not in historico

    def test_a_refused_registration_masks_nothing_and_sets_no_flag(self, mundo):
        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_identificacao", campo="cpf", valor="111.111.111-11")),  # invalid CPF
            say("Esse CPF não confere."),
        ])
        r = _turno_identificacao(chan, f"CPF {CPF}")
        assert r["identificacao_registrada"] is False
        assert CPF in _blob(_linhas(chan, r))

    def test_the_flag_is_false_by_default_when_nothing_was_registered(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[say("Oi!")]))
        assert chan.turn(turn_body("Oi")).json()["identificacao_registrada"] is False


class TestFailureIsVisible:
    def test_a_failing_store_never_blocks_the_reply_is_logged_by_type_and_booked_as_an_event(self, mundo, caplog):
        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_identificacao", campo="cpf", valor=CPF)),
            say("Anotado."),
        ])
        store = chan.rt.stores.messages

        def quebra(org_id, conversation_id, valores):
            raise RuntimeError(f"db down while masking {valores[0]}")

        store.redigir_identificacao = quebra
        with caplog.at_level(logging.ERROR):
            r = _turno_identificacao(chan, f"CPF {CPF}")
        assert r["status"] == "respondido" and r["identificacao_registrada"] is True
        log = "\n".join(rec.getMessage() for rec in caplog.records)
        assert "identificacao_redacao_falhou" in log and "RuntimeError" in log
        assert CPF not in log and CPF_DIGITOS not in log and "db down" not in log
        eventos = [x.texto for x in _linhas(chan, r) if x.role == "evento"]
        assert turno_mod.EVENTO_REDACAO_FALHOU in eventos
        # the 046 CHECK on ``evento`` rows (a code, never prose) accepts it
        assert re.fullmatch(r"[a-z][a-z0-9_]*:[a-z0-9_]+(,[a-z0-9_]+)*", turno_mod.EVENTO_REDACAO_FALHOU)


class TestNoSurfaceReturnsTheRawNumber:
    def test_thread_read_conversation_read_and_handoff_carry_no_raw_number(self, mundo):
        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_identificacao", campo="cpf", valor=CPF)),
            say("Anotado."),
        ])
        r = _turno_identificacao(chan, f"Meu CPF é {CPF}")
        tid = r["thread_id"]
        with chan.as_token("agents:channel-status"):
            for path in (f"/api/channels/threads/{tid}", f"/api/channels/threads/{tid}/handoffs"):
                resp = chan.request("GET", path)
                assert resp.status_code == 200, path
                assert CPF not in resp.text and CPF_DIGITOS not in resp.text, path
        for path in (f"/api/conversations/{tid}/messages", f"/api/studio/threads/{tid}/mensagens"):
            resp = chan.rt.get(path)
            assert resp.status_code == 200, (path, resp.text)
            assert "***" in resp.text and CPF not in resp.text and CPF_DIGITOS not in resp.text, path


class TestRealtimeStreamIsPurged:
    def test_a_reconnecting_subscriber_never_receives_the_raw_number(self, mundo):
        import asyncio

        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_identificacao", campo="cpf", valor=CPF)),
            say("Anotado."),
        ])
        r = _turno_identificacao(chan, f"Meu CPF é {CPF}")
        tid = r["thread_id"]
        assert r["identificacao_registrada"] is True
        retained = json.dumps([e.payload for e in chan.events(tid)], default=str, ensure_ascii=False)
        assert CPF not in retained and CPF_DIGITOS not in retained

        from app.realtime import conversation_scope
        from noctusai_lib.realtime import RealtimeEvent  # noqa: F401

        async def reconectar():
            sub = chan.rt.stores.bus.subscribe(conversation_scope(UUID(tid)), last_event_id="0-0")
            vistos = []
            try:
                while len(vistos) < len(chan.events(tid)):
                    vistos.append(await asyncio.wait_for(sub.__anext__(), timeout=2))
            finally:
                await sub.aclose()
            return vistos

        replay = json.dumps([e.payload for e in asyncio.run(reconectar())], default=str, ensure_ascii=False)
        assert CPF not in replay and CPF_DIGITOS not in replay
        # the assistant's own message.new (published AFTER registration) is still there
        assert any(e.event == "message.new" for e in chan.events(tid))

    def test_a_bus_failure_never_blocks_the_reply_and_logs_type_only(self, mundo, caplog):
        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_identificacao", campo="cpf", valor=CPF)),
            say("Anotado."),
        ])

        async def quebra(scope, predicate):
            raise RuntimeError(f"redis down {CPF_DIGITOS}")

        chan.rt.stores.bus.redact = quebra
        with caplog.at_level(logging.ERROR):
            r = _turno_identificacao(chan, f"Meu CPF é {CPF}")
        assert r["status"] == "respondido" and r["identificacao_registrada"] is True
        log = "\n".join(rec.getMessage() for rec in caplog.records)
        assert "realtime.redact_failed" in log and "RuntimeError" in log and CPF_DIGITOS not in log
        assert CPF not in _blob(_linhas(chan, r))  # the store was still masked
