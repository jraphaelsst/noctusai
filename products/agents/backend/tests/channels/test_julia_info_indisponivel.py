"""Raw placeholders never reach a model or a lead; a REQUIRED org spec with no value is a runtime safety net, not a
refusal: the prompt carries the INDISPONIVEL sentinel, the org is alerted (deduped per step), a lead who insists and
accepts a person is handed off with ``info_indisponivel`` and the org is told again."""
from __future__ import annotations

from uuid import UUID

from noctusai_lib.integrations.llm import FakeProvider

from app.stores.studio_definitions import SectionInput
from app.stores.studio_definitions_conteudo import SpecDefInput
from app.studio.especificacoes import SPEC_INDISPONIVEL
from tests.channels.conftest import turn_body
from tests.channels.julia_v2 import PLAT_ORG
from tests.channels.test_julia_v2_e2e import call, say, step
from tests.studio.rt.fakes import publish

SECAO = "O retorno de um corretor leva {{org.prazo}}. Atendemos {{org.cidade}}."


def _mundo(chan, *, prazo_obrigatorio=True, valores=None):
    studio = chan.rt.studio
    chan.seed_agent(publish=False)
    d = studio.get_platform_definition("julia")
    draft = studio.get_draft(PLAT_ORG, d.id)
    studio.replace_sections(PLAT_ORG, draft.id, [SectionInput("persona", "Persona", 10, SECAO)])
    studio.replace_spec_defs(PLAT_ORG, draft.id, [
        SpecDefInput("prazo", "Prazo", tipo="texto_curto", obrigatoria=prazo_obrigatorio),
        SpecDefInput("cidade", "Cidade", tipo="texto_curto", obrigatoria=False)])
    publish(studio, PLAT_ORG, d, draft.id, UUID(int=7))
    if valores:
        studio.upsert_org_specs(chan.org_id, "julia", valores)


def _sistema(chan) -> str:
    return chan.provider.calls[0]["messages"][0].content


def _alertas(resp):
    return [a for a in resp["actions"] if a["type"] == "alerta"]


class TestRequiredSpecMissingDoesNotRefuse:
    def test_the_turn_runs_with_the_sentinel_never_a_raw_placeholder_and_the_org_is_alerted_once(self, chan):
        _mundo(chan)
        chan.use_provider(FakeProvider(tool_responses=[say("Vou verificar e volto. Qual o bairro?"), say("Qual o bairro?")]))
        r1 = chan.turn(turn_body("Em quanto tempo me retornam?", ids=["a1"]))
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body["status"] == "respondido"
        sistema = _sistema(chan)
        assert "{{org." not in sistema
        assert "[dado: prazo]" in sistema and f'"prazo": "{SPEC_INDISPONIVEL}"' in sistema
        [alerta] = _alertas(body)
        assert alerta["tipo"] == "outro" and "prazo" in alerta["descricao"]
        # the same missing key in the same conversation: no second `aviso`
        body2 = chan.turn(turn_body("E então?", ids=["a2"])).json()
        assert _alertas(body2) == []

    def test_an_optional_spec_with_no_value_is_omitted_not_rendered_raw_and_raises_no_alert(self, chan):
        _mundo(chan, prazo_obrigatorio=False)
        chan.use_provider(FakeProvider(tool_responses=[say("Oi! Qual o bairro?")]))
        body = chan.turn(turn_body("Oi", ids=["b1"])).json()
        assert body["status"] == "respondido" and _alertas(body) == []
        assert "{{org." not in _sistema(chan)

    def test_a_present_value_is_untouched_by_the_policy(self, chan):
        _mundo(chan, valores={"prazo": "1 dia útil", "cidade": "Santos"})
        chan.use_provider(FakeProvider(tool_responses=[say("Qual o bairro?")]))
        body = chan.turn(turn_body("Oi", ids=["c1"])).json()
        assert _alertas(body) == [] and SPEC_INDISPONIVEL not in _sistema(chan)


class TestInsistAcceptHandoff:
    def test_a_handoff_for_the_missing_info_alerts_the_org_a_second_time_with_the_redirect(self, chan):
        _mundo(chan)
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("handoff", motivo_codigo="info_indisponivel", motivo="O lead quer o prazo de retorno")),
            say("Vou passar para a equipe, um corretor entra em contato.")]))
        body = chan.turn(turn_body("Sim, quero falar com uma pessoa.", ids=["d1"])).json()
        assert [a for a in body["actions"] if a["type"] == "handoff"][0]["motivo_codigo"] == "info_indisponivel"
        etapas = [a["descricao"] for a in _alertas(body)]
        assert len(etapas) == 2 and any("aviso" in e for e in etapas) and any("redirecionado" in e for e in etapas)


class TestOutputGuard:
    def test_a_reply_with_a_raw_placeholder_is_blocked_rerun_and_the_clean_rerun_is_sent(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[
            say("O retorno é em {{org.prazo_retorno_humano}}. Qual o bairro?"), say("Qual o bairro?")]))
        body = chan.turn(turn_body("Prazo?", ids=["e1"])).json()
        assert body["reply"]["partes"] == ["Qual o bairro?"]
        assert {"regra": "placeholder_cru", "politica": "bloquear", "bloqueada": True} in body["conformidade"]["violacoes"]

    def test_the_data_pointer_is_never_sent_either_and_twice_means_silence_and_a_handoff(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[say("Prazo: [dado: prazo]"), say("De novo [dado: prazo]")]))
        body = chan.turn(turn_body("Prazo?", ids=["f1"])).json()
        assert body["reply"] is None or not body["reply"]["partes"]
        assert "[dado:" not in str(body.get("reply"))
        assert any(a["type"] == "handoff" for a in body["actions"])
