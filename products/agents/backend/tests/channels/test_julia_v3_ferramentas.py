"""Julia v3 (CONTRACT §12.3 / §12.4 / §12.6 / §12.8): ``sinalizar_alerta``, the hand-off ``relatorio``,
``qualificacao.imoveis_oferecidos``, the CPF-only identification, ``registrar_documento``. The report's narrative is
the Fake generator behind the ``get_relatorio_resumo_factory_dep`` seam (never the scripted provider)."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import jsonschema
import pytest
from noctusai_lib.integrations.llm import FakeProvider

from noctusai_lib.testing.migrations import migration_sql

from app.channels import relatorio as rel
from app.channels.relatorio import FakeResumoRelatorio
from app.qualificacao.identificacao import obrigatorios_do_padrao
from app.schemas import channels_contract
from tests.channels.conftest import contexto_body, turn_body
from tests.channels.test_julia_v2_e2e import (  # noqa: F401 -- ``mundo`` is the fixture
    call, ctx_campanha, mundo, say, step, tool_results,
)
from tests.channels.test_julia_v2_redacao_identificacao import (  # noqa: F401
    CPF, _ate_a_identificacao, _linhas, _turno_identificacao,
)

BACKEND = Path(__file__).resolve().parents[2]


def _acoes(resp: dict, tipo: str) -> list[dict]:
    return [a for a in resp["actions"] if a["type"] == tipo]


class TestSinalizarAlerta:
    def test_one_alert_per_tipo_per_turn_is_persisted_and_emitted(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("sinalizar_alerta", tipo="lead_insatisfeito", descricao="Lead irritado com a demora"),
                 call("sinalizar_alerta", tipo="lead_insatisfeito", descricao="de novo"),
                 call("sinalizar_alerta", tipo="erro_agente", descricao="Repeti uma pergunta", trecho="qual o bairro?")),
            say("Desculpe o erro! Posso chamar alguém da equipe?")]))
        r = chan.turn(turn_body("Já falei isso, que demora!")).json()
        alertas = _acoes(r, "alerta")
        assert [(a["tipo"], a["descricao"]) for a in alertas] == [
            ("lead_insatisfeito", "Lead irritado com a demora"), ("erro_agente", "Repeti uma pergunta")]
        assert set(alertas[0]) == {"seq", "type", "tipo", "descricao", "alerta_id"}
        rows = chan.alertas.listar(chan.org_id, UUID(r["thread_id"]))
        assert [(x.tipo, str(x.id)) for x in rows] == [(a["tipo"], a["alerta_id"]) for a in alertas]
        assert rows[1].trecho == "qual o bairro?" and rows[0].agent_id == chan.agent.id

    def test_an_unknown_tipo_is_refused_by_the_schema(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("sinalizar_alerta", tipo="inventado", descricao="x")), say("ok")]))
        r = chan.turn(turn_body("Oi")).json()
        assert not _acoes(r, "alerta") and tool_results(chan.provider)[0]["codigo"] == "argumentos_invalidos"


class TestRelatorio:
    def _ate_o_handoff(self, chan, *extra, midia=None, texto="Quero falar com alguém"):
        _ate_a_identificacao(chan, [*extra, step(call("handoff", motivo_codigo="pedido_humano", motivo="Quer um corretor")),
                                    say("Já chamo alguém.")])
        return _turno_identificacao(chan, texto, midia=midia)

    def test_handoff_carries_the_report_with_the_deterministic_parts(self, mundo):
        chan = mundo
        chan.resumo_relatorio = FakeResumoRelatorio("O lead busca apartamento em Pinheiros.")
        r = self._ate_o_handoff(chan)
        assert r["status"] == "handoff"
        [h] = _acoes(r, "handoff")
        rp = h["relatorio"]
        assert set(rp) == {"texto", "resumo_conversa", "perfil", "imoveis_oferecidos", "imoveis_recomendados",
                           "disponibilidade_visita", "identificacao", "motivo", "proximos_passos"}
        assert rp["resumo_conversa"] == "O lead busca apartamento em Pinheiros." and chan.resumo_relatorio.chamadas == 1
        assert [i["codigo"] for i in rp["imoveis_oferecidos"]] == ["B1", "B2", "B3"]
        assert {i["codigo"]: i["reacao"] for i in rp["imoveis_oferecidos"]} == {
            "B1": "gostou", "B2": "sem_reacao", "B3": "sem_reacao"}
        assert rp["imoveis_oferecidos"][0]["link"] == "https://imob.exemplo/B1"
        assert rp["imoveis_recomendados"] == ["B1", "B2", "B3"]  # liked first, at most 3
        assert rp["disponibilidade_visita"] == "sábado"  # the lead's own option; Julia schedules nothing
        assert rp["identificacao"] == {"cpf": False, "rg": False, "email": False, "documento_enviado": False}
        assert rp["motivo"] == "Quer um corretor" and "Fulano da Silva" in rp["texto"] and len(rp["texto"]) <= 1500
        assert "sábado" in rp["texto"] and "B1" in rp["texto"] and "Resumo: O lead busca" in rp["texto"]
        [nota] = chan.threads.list_handoffs(chan.org_id, UUID(r["thread_id"]))
        assert nota.perfil["relatorio"] == rp  # persisted on the hand-off note

    def test_a_failing_generation_degrades_to_a_deterministic_text_and_the_handoff_still_goes(self, mundo):
        chan = mundo
        chan.resumo_relatorio = FakeResumoRelatorio(falhar=True)
        r = self._ate_o_handoff(chan)
        assert r["status"] == "handoff"
        rp = _acoes(r, "handoff")[0]["relatorio"]
        assert rp["resumo_conversa"] is None and rp["texto"] and "Resumo:" not in rp["texto"]
        assert rel.AUDITORIA_DEGRADADO in [x.texto for x in _linhas(chan, r) if x.role == "evento"]

    def test_a_registered_name_overrides_the_forms_in_the_header(self, mundo):
        chan = mundo
        r = self._ate_o_handoff(
            chan, step(call("registrar_identificacao", campo="nome", valor="Maria Souza")),
            texto="Meu nome é Maria Souza, o outro é da empresa")
        assert "Relatório Julia — Maria Souza" in _acoes(r, "handoff")[0]["relatorio"]["texto"]

    def test_lead_pronto_carries_the_report_and_cpf_alone_completes_the_identity(self, mundo):
        chan = mundo
        r = self._ate_o_handoff.__func__ if False else None  # noqa: F841 -- (kept simple: dedicated scenario below)
        _ate_a_identificacao(chan, [
            step(call("registrar_identificacao", campo="cpf", valor=CPF)), step(call("concluir_qualificacao")),
            say("Perfeito, um corretor continua daqui.")])
        r = _turno_identificacao(chan, f"Meu CPF é {CPF}")
        [lp] = _acoes(r, "lead_pronto")
        assert r["status"] == "concluido" and lp["relatorio"]["identificacao"]["cpf"] is True
        assert CPF not in json.dumps(r) and "52998224725" not in json.dumps(r)  # flags only, never a value

    def test_the_text_is_capped_at_1500_chars_shrinking_the_narrative_first(self):
        texto = rel._texto(nome="A", telefone="+55", origem=None, resumo="x" * 3000, perfil={}, oferecidos=[],
                           recomendados=[], disponibilidade=None, ident={}, motivo="m", proximos="p")
        assert len(texto) <= rel.RELATORIO_TEXTO_MAX and "Motivo: m" in texto


class TestOffers:
    def test_the_turn_response_lists_every_property_offered_so_far_in_order(self, mundo):
        chan = mundo
        _ate_a_identificacao(chan, [say("ok")])
        r = _turno_identificacao(chan, "ok")
        assert r["qualificacao"]["imoveis_oferecidos"] == ["B1", "B2", "B3"]

    def test_a_turn_with_no_offers_lists_none(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[say("Oi!")]))
        assert chan.turn(turn_body("Oi")).json()["qualificacao"]["imoveis_oferecidos"] == []


class TestIdentificacao:
    def test_avaliar_lead_splits_required_from_desired_and_never_asks_a_name_the_contact_has(self, mundo):
        chan = mundo
        _ate_a_identificacao(chan, [step(call("avaliar_lead")), say("ok")])
        _turno_identificacao(chan, "ok")
        r = [x for x in tool_results(chan.provider) if "identificacao_desejada" in x][-1]
        assert r["identificacao_faltando"] == ["cpf"] and r["identificacao_desejada"] == ["rg", "email"]

    def test_without_a_contact_name_the_name_is_desired(self, mundo):
        chan = mundo
        _ate_a_identificacao(chan, [step(call("avaliar_lead")), say("ok")])
        body = turn_body("ok", ids=["m3"], contexto=ctx_campanha(), contact={"phone_e164": "+5511999990000"})
        chan.turn(body)
        r = [x for x in tool_results(chan.provider) if "identificacao_desejada" in x][-1]
        assert r["identificacao_desejada"] == ["rg", "email", "nome"]

    def test_the_standard_default_requires_only_the_cpf(self):
        from tests.channels.julia_v2 import versao_com_identidade

        assert obrigatorios_do_padrao(versao_com_identidade().criterios) == ("cpf",)
        assert obrigatorios_do_padrao(()) == ("cpf",)


class TestRegistrarDocumento:
    MIDIA = {"tipo": "imagem", "texto_extraido": "", "legenda": "meu RG"}

    def test_a_photo_of_the_id_satisfies_the_cpf_pending_extraction_and_emits_the_action(self, mundo):
        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_documento", provider_message_id="m3", tipo_provavel="rg")), say("Recebi, obrigada!")])
        r = _turno_identificacao(chan, "segue", midia=self.MIDIA)
        [d] = _acoes(r, "documento_identificacao")
        assert d == {"seq": d["seq"], "type": "documento_identificacao", "provider_message_id": "m3",
                     "tipo_provavel": "rg"}
        ref = chan.lead_ref().id
        assert chan.ident.faltando(chan.org_id, ref, ("cpf",)) == () and chan.ident.documento_enviado(chan.org_id, ref)
        assert r["identificacao_registrada"] is True

    @pytest.mark.parametrize("pmid,midia,codigo", [
        ("nao-existe", {"tipo": "imagem"}, "documento_nao_encontrado"),
        ("m3", {"tipo": "audio", "texto_extraido": "oi"}, "documento_sem_midia"),
    ])
    def test_an_id_that_is_not_a_lead_image_or_document_is_refused(self, mundo, pmid, midia, codigo):
        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_documento", provider_message_id=pmid, tipo_provavel="cnh")), say("Não consegui.")])
        r = _turno_identificacao(chan, "segue", midia=midia)
        assert not _acoes(r, "documento_identificacao")
        res = tool_results(chan.provider)[-1]
        assert res["codigo"] == codigo and res["mensagem"]  # no row written for the optional code: the bare code
        assert not chan.ident.documento_enviado(chan.org_id, chan.lead_ref().id)

    def test_a_message_of_the_assistant_is_not_a_document(self, mundo):
        chan = mundo
        _ate_a_identificacao(chan, [
            step(call("registrar_documento", provider_message_id="id-do-assistente", tipo_provavel="rg")), say("ok")])
        r = _turno_identificacao(chan, "oi")
        assert not _acoes(r, "documento_identificacao")


class TestContractFile:
    def test_a_turn_with_an_alert_validates_against_the_generated_contract(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("sinalizar_alerta", tipo="desvio", descricao="Fugiu do assunto")), say("Vamos voltar?")]))
        resp = chan.turn(turn_body("Qual a capital da França?", contexto=contexto_body())).json()
        schema = json.loads(Path(channels_contract.CONTRACT_PATH).read_text(encoding="utf-8"))["ChannelTurnResponse"]
        jsonschema.validate(resp, schema)

    def test_migration_057_is_service_role_only_and_matches_the_vocabularies(self):
        sql = migration_sql(BACKEND, "julia_v3_alertas_documentos")
        assert "ENABLE ROW LEVEL SECURITY" in sql and "REVOKE ALL ON agents.thread_alertas FROM PUBLIC, anon, authenticated" in sql
        for v in ("lead_insatisfeito", "erro_agente", "desvio", "outro", "'rg', 'cpf', 'cin', 'cnh'"):
            assert v in sql
