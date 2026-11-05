"""The tool registry and its enforcement (CONTRACT §3.4 / §3.5 E2): descriptions from rows, the schema in code,
server-side scoping, the skill gate, the refusal / error budgets and the safe stop, the offer cap."""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence
from uuid import UUID

import pytest
from noctusai_lib.integrations.llm import FakeProvider

from app.channels.tool_registry import TOOLS, schema_de
from app.studio.ferramentas_registry import FERRAMENTAS_CONHECIDAS
from app.studio.models import ConteudoBundle, FerramentaData
from tests.channels.conftest import contexto_body, turn_body
from tests.channels.test_julia_v2_e2e import (
    ScriptedSW, call, imovel, say, step, tool_results,
)

PERFIL_OPERACAO = {"criterio": "operacao", "valor": "compra", "trecho": "Quero comprar"}


def tools_offered(provider: FakeProvider) -> list[str]:
    first = next(c for c in provider.calls if c["method"] == "chat_with_tools")
    return [t.name for t in first["tools"]]


def first_tools(provider: FakeProvider) -> dict[str, Any]:
    first = next(c for c in provider.calls if c["method"] == "chat_with_tools")
    return {t.name: t for t in first["tools"]}


@pytest.fixture
def gated(chan):
    chan.seed_agent(obrigatoria={"registrar_perfil": "qualificar-lead", "oferecer_imoveis": "ofertar-imoveis"})
    chan.sw = ScriptedSW([[imovel("B1"), imovel("B2"), imovel("B3")]])
    from app.dependencies import get_julia_tools_client_dep
    from app.main import app

    app.dependency_overrides[get_julia_tools_client_dep] = lambda: chan.sw
    chan.sw.julia_token_orgs.add(chan.org_id)
    return chan


class TestTheRegistryIsSchemaInCodeWordsInRows:
    def test_every_registry_tool_is_a_known_tool_name(self):
        assert set(TOOLS) <= FERRAMENTAS_CONHECIDAS
        for retired in ("salvar_slots", "definir_operacao", "qualificar_lead", "pedido_visita", "horarios_visita"):
            assert retired not in TOOLS and retired not in FERRAMENTAS_CONHECIDAS

    def test_a_derived_schema_has_no_prose_unless_the_row_supplies_it(self):
        def keys(n):
            if isinstance(n, dict):
                return set(n) | {k for v in n.values() for k in keys(v)}
            if isinstance(n, list):
                return {k for v in n for k in keys(v)}
            return set()

        for nome in TOOLS:
            assert not {"description", "title", "default", "$ref", "$defs"} & keys(schema_de(nome))

    def test_the_model_sees_the_row_descriptions_and_the_enum_labels(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[say("Oi?")]))
        chan.turn()
        tools = first_tools(chan.provider)
        assert tools["handoff"].description == "desc:handoff"
        props = tools["handoff"].parameters["properties"]
        assert props["motivo"]["description"] == "short reason"
        assert props["motivo_codigo"]["description"].startswith("reason code pedido_humano: asks for a person")
        assert props["motivo_codigo"]["enum"] == [
            "pedido_humano", "reclamacao", "assunto_sensivel", "parceria", "fora_do_escopo", "outro",
            "seguranca", "direito_titular"]
        item = tools["registrar_perfil"].parameters["properties"]["itens"]
        assert item["description"] == "answers" and item["items"]["properties"]["trecho"]["description"] == "lead's words"
        for name in ("abrir_skill", "avaliar_lead", "registrar_perfil", "oferecer_imoveis", "handoff", "encerrar"):
            assert tools[name].description == f"desc:{name}"
        assert tools["avaliar_lead"].parameters["properties"] == {}

    def test_a_tool_without_an_active_row_is_not_offered_there_is_no_default_description(self, chan):
        chan.seed_agent(sem_ferramentas=("encerrar", "captacao"))
        chan.use_provider(FakeProvider(tool_responses=[say("Oi?")]))
        chan.turn()
        names = tools_offered(chan.provider)
        assert "encerrar" not in names and "captacao" not in names and "handoff" in names

    def test_the_retired_tools_are_never_offered(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[say("Oi?")]))
        chan.turn(turn_body(contexto={**contexto_body(), "acoes": ["salvar_slots", "pedido_visita"],
                                      "ferramentas": ["buscar_imoveis", "horarios_visita"]}))
        names = tools_offered(chan.provider)
        assert not {"salvar_slots", "definir_operacao", "qualificar_lead", "pedido_visita", "horarios_visita",
                    "buscar_imoveis"} & set(names)
        assert "consentimento_credito" not in names  # only with the credit analysis active

    def test_credit_consent_is_offered_only_when_the_org_uses_the_analysis(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[say("Oi?")]))
        chan.turn(turn_body(contexto=contexto_body(credito={"ativo": True, "consentimento": None})))
        assert "consentimento_credito" in tools_offered(chan.provider)

    def test_sw_tools_follow_the_orgs_tools_token_and_the_capability(self, chan):
        chan.seed_agent()
        chan.sw.julia_token_orgs.clear()
        chan.use_provider(FakeProvider(tool_responses=[say("Oi?")]))
        chan.turn()
        assert not {"oferecer_imoveis", "detalhes_imovel", "consultar_empreendimento"} & set(tools_offered(chan.provider))
        chan.sw.julia_token_orgs.add(chan.org_id)
        chan.use_provider(FakeProvider(tool_responses=[say("Oi?")]))
        chan.turn(turn_body(ids=["x2"], contexto={**contexto_body(), "capacidades": {"ferramentas_sw": False}}))
        assert "oferecer_imoveis" not in tools_offered(chan.provider)
        chan.use_provider(FakeProvider(tool_responses=[say("Oi?")]))
        chan.turn(turn_body("Quero ver apartamentos na zona sul", ids=["x3"]))
        assert "oferecer_imoveis" in tools_offered(chan.provider)

    def test_an_optional_enum_parameter_carries_its_value_labels_too(self):
        """``Literal[...] | None`` is ``anyOf: [{enum}, {null}]`` in the schema; its labels must still be rendered
        (A-polish #5) -- before, only a REQUIRED enum got them."""
        props = schema_de("captacao", {"operacao": "operação", "operacao.venda": "quer vender",
                                       "operacao.aluguel": "quer alugar"})["properties"]
        assert props["operacao"]["description"] == "operação venda: quer vender; aluguel: quer alugar"

    def test_the_model_cannot_name_an_org_or_a_lead(self, chan):
        chan.seed_agent()
        for nome, d in TOOLS.items():
            props = schema_de(nome)["properties"]
            assert not {"org_id", "lead_ref_id", "lead_id", "thread_id", "agent_id", "interacao_id"} & set(props), nome
            assert schema_de(nome)["additionalProperties"] is False
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("avaliar_lead", lead_ref_id="00000000-0000-0000-0000-000000000009", org_id="x")),
            say("Oi?"),
        ]))
        chan.turn()
        [res] = [r for r in tool_results(chan.provider) if r.get("codigo")]
        assert res["codigo"] == "argumentos_invalidos"
        assert res["mensagem"].startswith("txt:ferramenta.resultado.argumentos_invalidos")


class TestSkillGating:
    def test_a_gated_tool_refuses_until_the_skill_is_opened_in_this_thread(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("registrar_perfil", itens=[PERFIL_OPERACAO])),
            step(call("abrir_skill", nome="qualificar-lead")),
            step(call("registrar_perfil", itens=[PERFIL_OPERACAO])),
            say("Entendi. Qual o bairro?"),
        ]))
        body = chan.turn(turn_body("Quero comprar um apartamento")).json()
        r = tool_results(chan.provider)
        assert r[0] == {"ok": False, "codigo": "skill_nao_aberta",
                        "mensagem": "txt:ferramenta.resultado.recusa.skill_nao_aberta qualificar-lead"} or (
            r[0]["codigo"] == "skill_nao_aberta" and "qualificar-lead" in r[0]["mensagem"])
        assert r[1]["ok"] is True and r[1]["nome"] == "qualificar-lead"  # abrir_skill returns the skill body
        assert r[2]["aceitos"] == ["operacao"]
        assert body["qualificacao"]["faltando"]  # computed from the record the gate let through

    def test_the_opening_is_recorded_per_thread_and_compiled_hash(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("abrir_skill", nome="qualificar-lead")), say("Oi?")]))
        body = chan.turn().json()
        tid = UUID(body["thread_id"])
        rows = chan.rt.stores.messages.list(chan.org_id, tid, limite=10)
        h = [m.compiled_hash for m in rows if m.role == "assistant"][-1]
        assert chan.threads.skill_aberta(chan.org_id, tid, "qualificar-lead", h)
        assert not chan.threads.skill_aberta(chan.org_id, tid, "ofertar-imoveis", h)
        assert not chan.threads.skill_aberta(chan.org_id, tid, "qualificar-lead", "sha256:outro")

    def test_a_new_publish_means_the_skill_must_be_opened_again(self, gated):
        from app.stores.studio_definitions import SectionInput
        from app.studio.catalog import StoreKnowledgeCatalog
        from tests.channels.julia_v2 import PLAT_ORG
        from tests.studio.rt.fakes import publish

        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[step(call("abrir_skill", nome="qualificar-lead")), say("Oi?")]))
        chan.turn(turn_body("Quero comprar", ids=["a"]))
        studio = chan.rt.studio
        draft = studio.create_draft(PLAT_ORG, chan.world.definicao.id, chan.version.id, chan.rt.user_id)
        studio.replace_sections(PLAT_ORG, draft.id, [SectionInput("persona", "Persona", 10, "Persona v2.")])
        publish(studio, PLAT_ORG, chan.world.definicao, draft.id, chan.rt.user_id,
                catalog=StoreKnowledgeCatalog(chan.rt.knowledge))
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("registrar_perfil", itens=[PERFIL_OPERACAO])), say("Qual o bairro?")]))
        chan.turn(turn_body("Quero comprar", ids=["b"]))
        assert tool_results(chan.provider)[0]["codigo"] == "skill_nao_aberta"

    def test_the_shared_library_can_gate_a_tool_through_obrigatoria_para(self, chan):
        """A-SKILLS plugs in through the ``SkillFonte`` interface; faked here."""

        class Biblioteca:
            async def abrir(self, nome):
                return {"nome": nome, "corpo": "..."}

            async def ler_arquivo(self, nome, caminho):
                return {"erro": "arquivo_inexistente", "disponiveis": []}

            def obrigatoria_para(self) -> Mapping[str, Sequence[str]]:
                return {"qualificar-lead": ["avaliar_lead"]}

        chan.seed_agent()
        chan.skills_factory = lambda *a: Biblioteca()
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("avaliar_lead")), step(call("abrir_skill", nome="qualificar-lead")), step(call("avaliar_lead")),
            say("Qual o bairro?")]))
        chan.turn(turn_body("Oi"))
        r = tool_results(chan.provider)
        assert r[0]["codigo"] == "skill_nao_aberta" and r[2]["ok"] is True and "estagio" in r[2]


class TestOtherGates:
    def test_offering_before_the_minimum_is_refused(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("abrir_skill", nome="ofertar-imoveis")), step(call("oferecer_imoveis", modo="similares")),
            say("Qual o bairro?")]))
        chan.turn(turn_body("Oi"))
        assert tool_results(chan.provider)[-1]["codigo"] == "nao_pode_ofertar"
        assert [n for _o, n, _a in chan.sw.julia_calls] == []

    def test_concluding_early_is_refused(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[step(call("concluir_qualificacao")), say("Qual o bairro?")]))
        body = chan.turn(turn_body("Oi")).json()
        assert tool_results(chan.provider)[0]["codigo"] == "estagio_nao_conclusivo"
        assert body["status"] == "respondido" and body["participante"]["estado"] == "ativo"

    def test_reacting_to_a_never_offered_code_is_refused(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("registrar_reacao_imovel", codigo="ZZ9", reacao="gostou")), say("Qual?")]))
        chan.turn(turn_body("Oi"))
        assert tool_results(chan.provider)[0]["codigo"] == "imovel_nao_oferecido"

    def test_identity_is_asked_only_once_the_standard_says_so(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("registrar_identificacao", campo="cpf", valor="529.982.247-25")), say("Qual o bairro?")]))
        chan.turn(turn_body("Meu CPF é 529.982.247-25"))
        assert tool_results(chan.provider)[0]["codigo"] == "identificacao_nao_devida"
        assert chan.ident.coletados(chan.org_id, chan.lead_ref().id) == frozenset()

    def test_the_name_is_registrable_at_any_point_it_is_not_sensitive(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("registrar_identificacao", campo="nome", valor="Maria Souza")), say("Qual o bairro?")]))
        chan.turn(turn_body("Meu nome é Maria Souza"))
        assert tool_results(chan.provider)[0]["status"] == "registrado"
        assert chan.ident.coletados(chan.org_id, chan.lead_ref().id) == frozenset({"nome"})

    def test_an_identity_value_not_in_the_leads_words_is_refused(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("registrar_perfil", itens=[PERFIL_OPERACAO])), say("ok")]))
        chan.turn(turn_body("Quero comprar"))
        # force the "visit intent" state directly in the store: an offered + wanted property
        from app.qualificacao.models import EventoImovel

        ref = chan.lead_ref().id
        chan.leads.adicionar_evento(chan.org_id, ref, agent_id=chan.agent.id, thread_id=None,
                                    evento=EventoImovel("B1", "oferecido", "similar", 1))
        chan.leads.adicionar_evento(chan.org_id, ref, agent_id=chan.agent.id, thread_id=None,
                                    evento=EventoImovel("B1", "quer_visitar", "similar"))
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("registrar_identificacao", campo="cpf", valor="529.982.247-25")), say("Qual seu CPF?")]))
        chan.turn(turn_body("Meu CPF eu prefiro passar depois", ids=["m2"]))
        assert tool_results(chan.provider)[0]["codigo"] == "valor_nao_confere"
        assert "cpf" not in chan.ident.coletados(chan.org_id, ref)

    def test_the_offer_cap_per_thread_is_data(self, gated):
        chan = gated
        chan.conformidade.definir_limites(chan.org_id, chan.agent.id, max_imoveis_distintos=2, max_oferecer_turno=2)
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("abrir_skill", nome="qualificar-lead"), call("abrir_skill", nome="ofertar-imoveis")),
            step(call("registrar_perfil", itens=[
                {"criterio": "operacao", "valor": "compra", "trecho": "Quero comprar"},
                {"criterio": "interesse_campanha", "valor": "aberto", "trecho": "aceito ver"},
                {"criterio": "regioes", "valor": ["Pinheiros"], "trecho": "Pinheiros"}])),
            step(call("oferecer_imoveis", modo="similares")),
            step(call("oferecer_imoveis", modo="similares")),
            say("Veja: https://imob.exemplo/B1 https://imob.exemplo/B2. Gostou?"),
        ]))
        chan.turn(turn_body("Quero comprar em Pinheiros, aceito ver outras"))
        ofertados = chan.qual.codigos_oferecidos(chan.org_id, chan.lead_ref().id)
        assert ofertados == ["B1", "B2"]  # three came back, the cap let two through
        assert tool_results(chan.provider)[-1]["codigo"] == "limite_ofertas"

    def test_a_reply_cites_only_what_the_tools_returned(self, gated):
        """The record of offered codes (not the model's say-so) decides what the thread may cite."""
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[say("Veja https://inventado.exemplo/XX. Gostou?")]))
        body = chan.turn(turn_body("Oi")).json()
        # a link no tool returned is link_nao_permitido's (blocks by default: no bubble, a hand-off); the
        # property-code half of imovel_sem_ferramenta keeps its own rule
        assert "link_nao_permitido" in {v["regra"] for v in body["conformidade"]["violacoes"]}
        assert not any("inventado.exemplo" in x for x in body["reply"]["partes"])  # the link never reached the lead
        assert any(v["regra"] == "link_nao_permitido" and v["bloqueada"] for v in body["conformidade"]["violacoes"])


class TestRetryBudgetAndSafeStop:
    def _refusals(self, n):
        """``n`` COUNTED refusals (trecho_nao_confere, skill already open): evidence the lead never gave."""
        falso = {**PERFIL_OPERACAO, "trecho": "frase que o lead nunca escreveu"}
        return [step(call("abrir_skill", nome="qualificar-lead")),
                *[step(call("registrar_perfil", itens=[falso])) for _ in range(n)]]

    def test_after_two_refusals_in_a_turn_the_turn_stops_with_a_handoff_and_a_flagged_event(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[*self._refusals(2), step(call("avaliar_lead")), say("nunca")]))
        body = chan.turn(turn_body("Quero comprar")).json()
        recusados = [x["codigo"] for r in tool_results(chan.provider) for x in r.get("recusados", [])]
        assert recusados == ["trecho_nao_confere"]  # the 2nd result is never re-sent: the stop answers first
        assert body["status"] == "handoff" and body["reply"]["partes"] == []  # silence: no text row, no code text
        [h] = body["actions"]
        assert (h["type"], h["motivo_codigo"]) == ("handoff", "limite_recusas")
        assert h["motivo"] == "txt:escalonamento.resumo limite_recusas".replace("{motivo_codigo}", "limite_recusas")
        assert body["participante"]["estado"] == "pausado"
        assert {"regra": "parada_segura", "politica": "registrar", "bloqueada": False} in body["conformidade"]["violacoes"]
        [nota] = chan.threads.list_handoffs(chan.org_id, UUID(body["thread_id"]))
        assert nota.motivo_codigo == "limite_recusas" and nota.para.tipo == "papel"
        calls = [c for c in chan.provider.calls if c["method"] == "chat_with_tools"]
        assert len(calls) == 3  # skill + 2 refusals; the next chat is answered by the stop, WITHOUT reaching the provider

    def test_the_stop_replies_with_the_db_text_when_the_owner_wrote_one(self, chan):
        from app.stores.studio_definitions_conteudo import TextoInput

        chan.seed_agent(obrigatoria={"registrar_perfil": "qualificar-lead"},
                        textos_extra=[TextoInput("runtime.parada_segura", "Já chamo alguém da equipe.")])
        chan.use_provider(FakeProvider(tool_responses=[*self._refusals(2), say("nunca")]))
        body = chan.turn(turn_body("Quero comprar")).json()
        assert body["reply"]["partes"] == ["Já chamo alguém da equipe."] and body["status"] == "handoff"

    def test_repeated_tool_errors_stop_the_turn_too(self, gated):
        chan = gated
        chan.sw.julia_fail = True
        chan.conformidade.definir_limites(chan.org_id, chan.agent.id, max_erros_ferramenta_por_turno=2)
        # SW tools answer "indisponivel" (a failure, not a refusal): detalhes_imovel x2
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("detalhes_imovel", codigo="A1")), step(call("detalhes_imovel", codigo="A2")), say("nunca")]))
        body = chan.turn(turn_body("Oi")).json()
        [h] = body["actions"]
        assert h["motivo_codigo"] == "falhas_repetidas" and body["status"] == "handoff"

    def test_the_budget_is_data(self, gated):
        chan = gated
        chan.conformidade.definir_limites(chan.org_id, chan.agent.id, max_recusas_por_turno=3)
        chan.use_provider(FakeProvider(tool_responses=[*self._refusals(2), say("Qual o bairro?")]))
        body = chan.turn(turn_body("Quero comprar")).json()
        assert body["status"] == "respondido"  # two refusals are within a budget of three


class TestRecusaCorrigivelNaoGastaOOrcamento:
    """A refusal the model fixes with a DIFFERENT call in the same turn is guidance, not abuse (Julia prod eval,
    2026-11-05: a greeting + two correctable refusals handed the lead off)."""

    def test_two_correctable_refusals_then_a_valid_call_complete_with_no_handoff(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("oferecer_imoveis", modo="campanha")),            # skill ofertar-imoveis not opened
            step(call("registrar_perfil", itens=[PERFIL_OPERACAO])),    # skill qualificar-lead not opened
            step(call("avaliar_lead")),                                 # the valid call
            say("Oi! Em que posso ajudar?")]))
        body = chan.turn(turn_body("Oi, vi o anúncio")).json()
        codigos = [r["codigo"] for r in tool_results(chan.provider) if r.get("codigo")]
        assert codigos == ["skill_nao_aberta", "skill_nao_aberta"]
        assert body["status"] == "respondido" and body["actions"] == []
        assert "limite_recusas" not in json.dumps(body)

    def test_a_correctable_refusal_does_not_spend_the_per_tool_budget(self, gated):
        """Prod: max_oferecer_turno=1. oferecer(campanha) is refused (no code), the corrected oferecer must still run."""
        chan = gated
        assert chan.conformidade.limites(chan.org_id, chan.agent.id).max_oferecer_turno == 1
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("abrir_skill", nome="qualificar-lead"), call("abrir_skill", nome="ofertar-imoveis")),
            step(call("registrar_perfil", itens=[
                {"criterio": "operacao", "valor": "compra", "trecho": "Quero comprar"},
                {"criterio": "interesse_campanha", "valor": "aberto", "trecho": "aceito ver"},
                {"criterio": "regioes", "valor": ["Pinheiros"], "trecho": "Pinheiros"}])),
            step(call("oferecer_imoveis", modo="campanha")),   # sem_codigo_campanha (correctable)
            step(call("oferecer_imoveis", modo="similares")),  # the correction: must not hit limite_ferramentas
            say("Veja: https://imob.exemplo/B1. Gostou?")]))
        body = chan.turn(turn_body("Quero comprar em Pinheiros, aceito ver outras")).json()
        codigos = [r.get("codigo") for r in tool_results(chan.provider)]
        assert "sem_codigo_campanha" in codigos and "limite_ferramentas" not in codigos
        assert chan.qual.codigos_oferecidos(chan.org_id, chan.lead_ref().id)  # the offer happened
        assert body["status"] == "respondido"

    def test_two_counted_refusals_still_stop_the_turn(self, gated):
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("abrir_skill", nome="qualificar-lead")),
            *[step(call("registrar_perfil", itens=[{**PERFIL_OPERACAO, "trecho": "nunca dito"}])) for _ in range(2)],
            say("nunca")]))
        body = chan.turn(turn_body("Oi")).json()
        assert body["status"] == "handoff" and body["actions"][0]["motivo_codigo"] == "limite_recusas"

    def test_an_unbounded_correctable_loop_still_hits_the_call_cap(self, gated):
        chan = gated
        chan.conformidade.definir_limites(chan.org_id, chan.agent.id, max_chamadas_ferramenta_turno=4)
        chan.use_provider(FakeProvider(tool_responses=[
            *[step(call("registrar_perfil", itens=[PERFIL_OPERACAO])) for _ in range(8)], say("nunca")]))
        body = chan.turn(turn_body("Quero comprar")).json()
        codigos = [r["codigo"] for r in tool_results(chan.provider) if r.get("codigo")]
        assert codigos[:4] == ["skill_nao_aberta"] * 4 and "limite_ferramentas" in codigos  # correctable ones free, the cap bites
        assert body["status"] == "handoff" or body["status"] == "silencio"

    def test_a_correctable_refusal_does_not_count_and_a_counted_one_does(self):
        from app.channels.tool_registry import _recusa

        class T:
            def texto(self, *a, **k):
                return "x"

        assert _recusa(T(), "skill_nao_aberta", skill="s").corrigivel is True
        assert _recusa(T(), "trecho_nao_confere").corrigivel is False
        assert _recusa(T(), "codigo_inventado_novo").corrigivel is False  # unclassified: fail-closed


class TestClassificacaoDasRecusas:
    def test_every_refusal_code_in_the_module_is_in_exactly_one_class(self):
        import ast
        import inspect

        from app.channels import tool_registry as tr
        from app.studio.textos_registry import CODIGOS_RECUSA, CODIGOS_RECUSA_OPCIONAIS

        tree = ast.parse(inspect.getsource(tr))
        usados: set[str] = set(CODIGOS_RECUSA) | set(CODIGOS_RECUSA_OPCIONAIS)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_recusa" and len(n.args) > 1:
                a = n.args[1]
                if isinstance(a, ast.Constant):
                    usados.add(a.value)
                elif isinstance(a, ast.BoolOp):  # ``r.codigo or "evento_invalido"``
                    usados |= {v.value for v in a.values if isinstance(v, ast.Constant)}
            if isinstance(n, ast.Dict):  # {"ok": False, "codigo": "<literal>", ...}
                for k, v in zip(n.keys, n.values):
                    if isinstance(k, ast.Constant) and k.value == "codigo" and isinstance(v, ast.Constant):
                        usados.add(v.value)
        assert tr.RECUSAS_CORRIGIVEIS.isdisjoint(tr.RECUSAS_CONTADAS)
        sem_classe = usados - tr.RECUSAS_CORRIGIVEIS - tr.RECUSAS_CONTADAS
        assert not sem_classe, f"unclassified refusal codes: {sorted(sem_classe)}"
        assert {"skill_nao_aberta", "sem_codigo_campanha"} <= tr.RECUSAS_CORRIGIVEIS
        assert {"trecho_nao_confere", "consentimento_sem_evidencia", "limite_ferramentas"} <= tr.RECUSAS_CONTADAS


class TestExhaustedLoopIsSilenceByDefault:
    def test_a_loop_that_hits_its_cap_sends_nothing_and_is_flagged(self, chan):
        chan.seed_agent()
        loop = [step(call("avaliar_lead")) for _ in range(12)]
        chan.use_provider(FakeProvider(tool_responses=loop))
        body = chan.turn().json()
        assert body["status"] == "silencio" and body["reply"]["partes"] == []
        assert "fallback_enviado" in [v["regra"] for v in body["conformidade"]["violacoes"]]

    def test_the_fallback_reply_is_the_db_text_when_the_owner_wrote_one(self, chan):
        from app.stores.studio_definitions_conteudo import TextoInput

        chan.seed_agent(textos_extra=[TextoInput("runtime.resposta_fallback", "Pode reformular?")])
        chan.use_provider(FakeProvider(tool_responses=[step(call("avaliar_lead")) for _ in range(12)]))
        body = chan.turn().json()
        assert body["reply"]["partes"] == ["Pode reformular?"]
        assert "fallback_enviado" in [v["regra"] for v in body["conformidade"]["violacoes"]]


def test_no_tool_description_or_prompt_text_lives_in_the_channel_code():
    """The keeper's promise, asserted on the files that used to hold the literals."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app"
    for rel in ("channels/tool_registry.py", "channels/contexto.py", "channels/turno.py", "channels/extracao.py",
                "runtime/llm_runtime.py", "routers/channels_router.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert not re.search(r"description\s*=\s*\(?\s*[\"']", src), rel  # no ToolSpec(description="...")
        assert not re.search(r"_SYSTEM\s*=\s*\(?\s*[\"']", src), rel
        assert "FALLBACK_REPLY" not in src, rel
    assert not (root / "channels" / "tools.py").exists()
    assert isinstance(ConteudoBundle, type) and isinstance(FerramentaData, type) and json  # imports are used
