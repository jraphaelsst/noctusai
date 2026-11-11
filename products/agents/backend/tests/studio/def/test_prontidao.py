"""Readiness of a draft (``app.studio.prontidao`` + ``GET /api/studio/agents/{key}/prontidao``).

Three layers:

* the PURE composer, driven with hand-built snapshots (no IO, no mocks);
* the route (auth strict, audit, shape);
* GATE <-> READINESS PARITY: every blocking item names the publish refusal it stands for, and for every state below
  ``pronto_para_publicar`` is true exactly when ``POST .../draft/publish`` answers 200, and the refusal code is the one
  the blocking item names. A blocking item with no refusal behind it (or a refusal with no item) fails here.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.config import settings
from app.services import runtime_settings
from app.stores.runtime_settings import FakeRuntimeSettingsStore
from app.stores.studio_evals import EvalCaseInput, FakeEvalStore
from app.studio.eval_mecanismo import MecanismoGateRun, MecanismoRequisito
from app.studio.models import CompiledPrompt, CompileWarning, GateRun
from app.studio import prontidao as pr
from app.studio.prontidao import AreaGeracao, Entrada, FerramentaLinha, PinSkill
from app.routers.studio_agents_router import get_eval_store_dep
from tests.julia_body import JULIA_BODY
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

BASE = "/api/studio/agents"
PLAT = "/api/studio/plataforma"
HASH = "sha256:atual"


def _compiled(*avisos: CompileWarning, hash_: str = HASH) -> CompiledPrompt:
    return CompiledPrompt(texto="x", hash=hash_, manifest=[], tokens_estimados=1, sob_demanda=[], avisos=list(avisos))


def _entrada(**kw) -> Entrada:
    base = dict(agent_key="a", version_id=uuid4(), compiled=_compiled(), limiar=0.8, usa_canais=False)
    return Entrada(**{**base, **kw})


def _juiz(score=0.9, hash_=HASH, **kw) -> GateRun:
    return GateRun(id=uuid4(), score=score, limiar=0.8, compiled_hash=hash_, status="concluida", completa=True, total=3, **kw)


def _mec(hash_=HASH, **kw) -> MecanismoGateRun:
    base = dict(id=uuid4(), compiled_hash=hash_, status="concluida", driver="live", completa=True, aprovado=True,
                orcamento_excedido=False, total_casos=4, casos_aprovados=4)
    return MecanismoGateRun(**{**base, **kw})


def _codigos(p: pr.Prontidao, sev=None) -> list[str]:
    return [i.codigo for i in p.itens if sev is None or i.severidade == sev]


# ── the pure composer ───────────────────────────────────────────────────────


class TestCompor:
    def test_a_clean_draft_with_a_green_judge_is_ready_and_has_no_blocking_item(self):
        p = pr.compor(_entrada(casos_comportamento=3, juiz=_juiz()))
        assert p.pronto_para_publicar and p.bloqueantes == 0
        assert "eval_juiz_ok" in _codigos(p, "ok")

    def test_blocking_compile_warnings_name_the_publish_refusal_advisory_ones_do_not(self):
        p = pr.compor(_entrada(
            compiled=_compiled(
                CompileWarning("texto_ausente", "falta", True),
                CompileWarning("secao_vazia", "vazia", True),
                CompileWarning("spec_nao_usada", "sobra", False),
            ),
            casos_comportamento=3, juiz=_juiz(),
        ))
        por_codigo = {i.codigo: i for i in p.itens if i.grupo == "compilador"}
        assert por_codigo["texto_ausente"].severidade == "bloqueante"
        assert por_codigo["texto_ausente"].recusa_publicacao == "conteudo_incompleto"
        assert por_codigo["secao_vazia"].recusa_publicacao == "compile_blocked"
        assert por_codigo["spec_nao_usada"].severidade == "aviso" and por_codigo["spec_nao_usada"].recusa_publicacao is None
        assert not p.pronto_para_publicar

    def test_compile_refusal_helper_agrees_with_the_items(self):
        assert pr.recusa_de_compilacao(_compiled()) is None
        assert pr.recusa_de_compilacao(_compiled(CompileWarning("spec_nao_usada", "x", False))) is None
        assert pr.recusa_de_compilacao(_compiled(CompileWarning("texto_ausente", "x", True))) == "conteudo_incompleto"
        assert pr.recusa_de_compilacao(_compiled(CompileWarning("secao_vazia", "x", True))) == "compile_blocked"

    @pytest.mark.parametrize("run,motivo", [
        (None, "sem_execucao"),
        (_juiz(hash_="sha256:antigo"), "hash_diferente"),
        (_juiz(score=0.5), "abaixo_do_limiar"),
        (GateRun(id=uuid4(), score=0.9, limiar=0.8, compiled_hash=HASH, status="concluida", completa=False, total=2), "incompleta"),
    ])
    def test_the_judge_suite_blocks_with_eval_required_and_says_why(self, run, motivo):
        p = pr.compor(_entrada(casos_comportamento=3, juiz=run))
        item = next(i for i in p.itens if i.codigo == f"eval_juiz_{motivo}")
        assert item.severidade == "bloqueante" and item.recusa_publicacao == "eval_required"
        assert pr.juiz_motivo(run, HASH, 0.8) == motivo and not pr.juiz_aprovado(run, HASH, 0.8)

    def test_no_active_judge_case_blocks_because_no_run_can_exist(self):
        p = pr.compor(_entrada(casos_comportamento=0))
        item = next(i for i in p.itens if i.codigo == "eval_sem_casos")
        assert item.severidade == "bloqueante" and item.recusa_publicacao == "eval_required"

    def test_under_the_mechanism_gate_the_judge_suite_is_advisory_unless_it_opted_in(self):
        mec = MecanismoRequisito(exigido=True, casos_ativos=4, run=_mec())
        consultivo = pr.compor(_entrada(casos_comportamento=3, juiz=None, mecanismo=mec))
        assert consultivo.pronto_para_publicar
        assert next(i for i in consultivo.itens if i.codigo == "eval_juiz_sem_execucao").severidade == "aviso"
        bloqueia = pr.compor(_entrada(
            casos_comportamento=3, juiz=None, mecanismo=MecanismoRequisito(exigido=True, casos_ativos=4, run=_mec(), comportamento_bloqueia=True)))
        assert not bloqueia.pronto_para_publicar

    @pytest.mark.parametrize("req,motivo", [
        (MecanismoRequisito(exigido=True, casos_ativos=0), "sem_casos"),
        (MecanismoRequisito(exigido=True, casos_ativos=4, run=None), "sem_execucao"),
        (MecanismoRequisito(exigido=True, casos_ativos=4, run=_mec(hash_="sha256:antigo")), "hash_diferente"),
        (MecanismoRequisito(exigido=True, casos_ativos=4, run=_mec(driver="fake")), "driver_nao_live"),
    ])
    def test_the_mechanism_suite_has_no_override_and_names_its_motivo(self, req, motivo):
        p = pr.compor(_entrada(casos_comportamento=3, juiz=_juiz(), mecanismo=req))
        item = next(i for i in p.itens if i.codigo == f"mecanismo_{motivo}")
        assert item.severidade == "bloqueante" and item.recusa_publicacao == "mecanismo_reprovado"
        assert item.detalhe["motivo"] == motivo

    def test_a_channel_agent_without_a_mechanism_suite_is_warned_not_blocked(self):
        p = pr.compor(_entrada(usa_canais=True, casos_comportamento=3, juiz=_juiz()))
        assert "mecanismo_nao_configurado" in _codigos(p, "aviso") and p.pronto_para_publicar

    def test_a_standard_without_a_published_version_blocks_only_when_the_draft_has_no_pin(self):
        livre = pr.compor(_entrada(padrao_chave="imob-lead", casos_comportamento=3, juiz=_juiz()))
        item = next(i for i in livre.itens if i.codigo == "qualificacao_indisponivel")
        assert item.severidade == "bloqueante" and item.recusa_publicacao == "qualificacao_indisponivel"
        fixado = pr.compor(_entrada(padrao_chave="imob-lead", padrao_fixado=True, casos_comportamento=3, juiz=_juiz()))
        assert "qualificacao_indisponivel" not in _codigos(fixado) and fixado.pronto_para_publicar

    def test_a_newer_standard_version_is_advisory(self):
        p = pr.compor(_entrada(
            padrao_chave="imob-lead", padrao_fixado=True, padrao_publicado=True, padrao_atualizacao=True,
            casos_comportamento=3, juiz=_juiz()))
        assert "padrao_atualizacao_disponivel" in _codigos(p, "aviso") and p.pronto_para_publicar

    def test_stale_skill_pins_are_advisory_and_point_at_the_explicit_action(self):
        p = pr.compor(_entrada(
            casos_comportamento=3, juiz=_juiz(), pins=(PinSkill("qualificar", 1, 2), PinSkill("fechar", 3, None))))
        itens = [i for i in p.itens if i.codigo == "skill_desatualizada"]
        assert [i.detalhe["skill"] for i in itens] == ["qualificar"]
        assert "Atualizar skills" in itens[0].acao_sugerida and p.pronto_para_publicar

    def test_expected_tools_without_a_row_and_unlabelled_parameters_are_advisory(self):
        esperadas = pr.ferramentas_esperadas(usa_canais=True, tem_skills=True, tool_policy={"knowledge": True}, com_padrao=True)
        assert {"abrir_skill", "handoff", "avaliar_lead", "kb_buscar"} <= set(esperadas)
        linhas = (FerramentaLinha("handoff", True, "Passa para uma pessoa.", {"motivo": "Por quê."}),)
        p = pr.compor(_entrada(
            casos_comportamento=3, juiz=_juiz(), ferramentas=linhas, ferramentas_esperadas={"handoff": "agente de canal", "encerrar": "agente de canal"},
            rotulos_ausentes=pr.rotulos_ausentes(linhas)))
        assert [i.detalhe["ferramenta"] for i in p.itens if i.codigo == "ferramenta_sem_descricao"] == ["encerrar"]
        assert p.pronto_para_publicar, "advisory items never block"

    def test_parameter_labels_are_judged_against_the_tool_schema(self):
        from app.channels.tool_registry import schema_de

        todos = {p: "rótulo" for p in schema_de("handoff")["properties"]}
        completo = FerramentaLinha("handoff", True, "d", todos)
        vazio = FerramentaLinha("handoff", True, "d", {})
        inativo = FerramentaLinha("encerrar", False, "d", {})
        sem_desc = FerramentaLinha("encerrar", True, "  ", {})
        fora = FerramentaLinha("kb_buscar", True, "d", {})
        assert pr.rotulos_ausentes([completo, inativo, sem_desc, fora]) == {}
        faltam = pr.rotulos_ausentes([vazio])["handoff"]
        assert set(faltam) == set(todos), "every property of the schema needs a label"
        parcial = FerramentaLinha("handoff", True, "d", {next(iter(todos)): "só um"})
        assert set(pr.rotulos_ausentes([parcial])["handoff"]) == set(todos) - {next(iter(todos))}
        assert "kb_buscar" not in pr.rotulos_ausentes([fora]), "a tool outside the code registry has no schema to judge"

    def test_generation_gaps_and_unfinished_areas_are_advisory(self):
        p = pr.compor(_entrada(
            casos_comportamento=3, juiz=_juiz(), geracao_status="parcial",
            geracao_areas=(
                AreaGeracao("textos", "concluida", None, ("texto_obrigatorio_ausente:x",)),
                AreaGeracao("evals", "pulado", "limite_de_custo", ()),
            )))
        assert {"geracao_lacunas", "geracao_area_nao_concluida"} <= set(_codigos(p, "aviso")) and p.pronto_para_publicar
        andamento = pr.compor(_entrada(casos_comportamento=3, juiz=_juiz(), geracao_status="executando"))
        assert "geracao_em_andamento" in _codigos(andamento, "aviso")

    def test_org_specs_and_controls(self):
        p = pr.compor(_entrada(
            usa_canais=True, casos_comportamento=3, juiz=_juiz(), specs_org_faltando=("agencia",), controle_modo="desligado"))
        assert {"spec_org_faltando", "controles_desligado"} <= set(_codigos(p, "aviso"))
        ligado = pr.compor(_entrada(usa_canais=True, casos_comportamento=3, juiz=_juiz(), controle_modo="ligado"))
        assert "controles_definidos" in _codigos(ligado, "ok")

    def test_items_come_blocking_first_and_the_composer_refuses_a_blocking_item_without_a_refusal(self):
        p = pr.compor(_entrada(compiled=_compiled(CompileWarning("secao_vazia", "x", True)), casos_comportamento=3, juiz=_juiz(),
                               pins=(PinSkill("a", 1, 2),)))
        sev = [i.severidade for i in p.itens]
        assert sev == sorted(sev, key=["bloqueante", "aviso", "ok"].index)
        assert pr.RECUSAS_PUBLICACAO == {
            "conteudo_incompleto", "compile_blocked", "mecanismo_reprovado", "eval_required", "qualificacao_indisponivel",
            "numero_fallback_ausente", "catalogo_ausente"}


class TestCatalogo:
    """081: an agent with ``oferecer_opcoes`` active needs a catalogue to offer from."""

    @staticmethod
    def _linhas(*nomes, ativo=True, descricao="Oferece."):
        return tuple(FerramentaLinha(n, ativo, descricao, {}) for n in nomes)

    def test_active_tool_and_no_catalogue_blocks_with_its_own_refusal(self):
        p = pr.compor(_entrada(ferramentas=self._linhas("oferecer_opcoes"), casos_comportamento=3, juiz=_juiz()))
        item = next(i for i in p.itens if i.codigo == "catalogo_ausente")
        assert item.severidade == "bloqueante" and item.recusa_publicacao == "catalogo_ausente" and not p.pronto_para_publicar

    def test_a_catalogue_the_factory_does_not_know_blocks_too(self):
        p = pr.compor(_entrada(ferramentas=self._linhas("oferecer_opcoes"), padrao_catalogo="inventado"))
        assert "catalogo_ausente" in _codigos(p, "bloqueante")

    @pytest.mark.parametrize("chave", ["imoveis_sw", "fixture"])
    def test_a_known_catalogue_is_ok(self, chave):
        p = pr.compor(_entrada(ferramentas=self._linhas("oferecer_opcoes"), padrao_catalogo=chave))
        assert "catalogo_definido" in _codigos(p, "ok") and "catalogo_ausente" not in _codigos(p)

    @pytest.mark.parametrize("linhas", [
        (), _linhas.__func__("oferecer_opcoes", ativo=False), _linhas.__func__("oferecer_opcoes", descricao=" "),
        _linhas.__func__("oferecer_imoveis", "detalhes_opcao"),
    ])
    def test_without_the_tool_active_and_described_it_says_nothing(self, linhas):
        assert not [i for i in pr.compor(_entrada(ferramentas=linhas)).itens if "catalogo" in i.codigo]

    def test_the_generic_tools_are_never_expected_of_an_agent_that_did_not_opt_in(self):
        # Julia (a standard + the channel) must not get "ferramenta_sem_descricao" for tools she never asked for
        esperadas = pr.ferramentas_esperadas(usa_canais=True, tem_skills=True, tool_policy={}, com_padrao=True)
        assert not {"oferecer_opcoes", "detalhes_opcao", "registrar_reacao_opcao"} & set(esperadas)
        assert {"avaliar_lead", "registrar_reacao_imovel"} <= set(esperadas)


# ── the route ───────────────────────────────────────────────────────────────


@pytest.fixture
def plat(studio):
    studio.store.mark_platform_org(DEFAULT_ORG_ID)
    studio.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": "admin", "org_role": "owner"}])
    r = studio.post(f"{PLAT}/agents", json={**JULIA_BODY, "key": "novo", "nome": "Novo", "owner_product": None, "padrao_qualificacao": None,
                                            "escopo_qualificacao": None})
    assert r.status_code == 201, r.text
    studio.evals = FakeEvalStore()
    studio.raw.app.dependency_overrides[get_eval_store_dep] = lambda: studio.evals
    return studio


def _get(studio, key="novo"):
    return studio.get(f"{BASE}/{key}/prontidao")


def _caso(studio, key="novo", slug="c1", **kw):
    agent = studio.store.get_agent(DEFAULT_ORG_ID, key)
    return studio.evals.create_case(
        DEFAULT_ORG_ID, agent.id, EvalCaseInput(slug=slug, titulo="t", entrada="e", criterios={"deve": ["x"], "nao_deve": []}, **kw))


class TestRoute:
    def test_unauthenticated_is_strict_401(self, plat):
        assert plat.raw.get(f"{BASE}/novo/prontidao").status_code == 401

    def test_an_org_admin_who_is_not_a_platform_admin_is_403(self, plat):
        plat.as_org_admin_only("owner")
        resp = _get(plat)
        assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required"

    def test_an_unknown_agent_is_404_and_an_agent_without_a_draft_is_404(self, plat):
        assert _get(plat, "nao-existe").status_code == 404
        agent = plat.store.get_agent(DEFAULT_ORG_ID, "novo")
        plat.store.discard_draft(DEFAULT_ORG_ID, plat.store.get_draft(DEFAULT_ORG_ID, agent.id).id)
        resp = _get(plat)
        assert resp.status_code == 404 and resp.json()["code"] == "draft_not_found"

    def test_an_empty_shell_reports_what_is_missing_and_is_not_ready(self, plat):
        resp = _get(plat)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pronto_para_publicar"] is False and body["bloqueantes"] >= 1 and body["agent_key"] == "novo"
        assert set(body) == {"agent_key", "version_id", "hash", "pronto_para_publicar", "bloqueantes", "avisos", "itens"}
        item = body["itens"][0]
        assert set(item) == {"codigo", "grupo", "severidade", "mensagem", "acao_sugerida", "recusa_publicacao", "detalhe"}
        codigos = {i["codigo"] for i in body["itens"]}
        assert {"sem_secoes", "eval_sem_casos"} <= codigos
        assert all(i["recusa_publicacao"] for i in body["itens"] if i["severidade"] == "bloqueante")

    def test_reading_it_is_audited_and_writes_nothing_else(self, plat):
        agent = plat.store.get_agent(DEFAULT_ORG_ID, "novo")
        antes = plat.store.get_draft(DEFAULT_ORG_ID, agent.id)
        assert _get(plat).status_code == 200
        depois = plat.store.get_draft(DEFAULT_ORG_ID, agent.id)
        assert depois.compiled_hash == antes.compiled_hash and depois.updated_at == antes.updated_at
        acoes = [(a.acao, (a.depois or {}).get("o_que")) for a in plat.store.list_audit_log(DEFAULT_ORG_ID, agent.id)]
        assert ("definicao_lida", "prontidao") in acoes


# ── gate <-> readiness parity ───────────────────────────────────────────────

SECOES = {"secoes": [{"chave": "persona", "titulo": "Quem você é", "ordem": 10, "conteudo": "Você ajuda.", "ativo": True}]}
#: the compiler-owned strings a content agent without skills/knowledge/web needs (test data only)
TEXTOS = {"itens": [
    {"chave": "compilador.titulo_ferramentas", "conteudo": "Ferramentas"},
    {"chave": "compilador.ferramenta_linha.web_desativada", "conteudo": "- Web: desligada."},
    {"chave": "compilador.ferramenta_linha.conhecimento_desativada", "conteudo": "- Conhecimento: desligado."},
]}


def _preencher(studio, key="novo"):
    assert studio.put(f"{BASE}/{key}/draft/sections", json=SECOES).status_code == 200
    assert studio.put(f"{BASE}/{key}/draft/textos", json=TEXTOS).status_code == 200


def _hash(studio, key="novo") -> str:
    return _get(studio, key).json()["hash"]


def _passar_juiz(studio, key="novo"):
    agent = studio.store.get_agent(DEFAULT_ORG_ID, key)
    draft = studio.store.get_draft(DEFAULT_ORG_ID, agent.id)
    run = GateRun(id=uuid4(), score=0.95, limiar=0.8, compiled_hash=_hash(studio, key), status="concluida", completa=True, total=1)
    studio.gate.set_run(DEFAULT_ORG_ID, draft.id, run)
    studio.store.register_eval_run(
        DEFAULT_ORG_ID, draft.id, run_id=run.id, score=0.95, compiled_hash=run.compiled_hash, completa=True, total=1)


def _mecanismo(studio, key="novo", **kw):
    agent = studio.store.get_agent(DEFAULT_ORG_ID, key)
    draft = studio.store.get_draft(DEFAULT_ORG_ID, agent.id)
    studio.gate.set_mecanismo(DEFAULT_ORG_ID, draft.id, MecanismoRequisito(exigido=True, casos_ativos=4, **kw))


def _cenario_vazio(studio):
    pass


def _cenario_sem_caso(studio):
    _preencher(studio)


def _cenario_sem_execucao(studio):
    _preencher(studio)
    _caso(studio)


def _cenario_juiz_abaixo(studio):
    _preencher(studio)
    _caso(studio)
    agent = studio.store.get_agent(DEFAULT_ORG_ID, "novo")
    draft = studio.store.get_draft(DEFAULT_ORG_ID, agent.id)
    studio.gate.set_run(DEFAULT_ORG_ID, draft.id, GateRun(
        id=uuid4(), score=0.2, limiar=0.8, compiled_hash=_hash(studio), status="concluida", completa=True, total=1))


def _cenario_mecanismo_sem_execucao(studio):
    _preencher(studio)
    _caso(studio)
    _passar_juiz(studio)
    _mecanismo(studio, run=None)


def _cenario_verde(studio):
    _preencher(studio)
    _caso(studio)
    _passar_juiz(studio)


def _cenario_verde_so_com_mecanismo(studio):
    _preencher(studio)
    _mecanismo(studio, run=MecanismoGateRun(
        id=uuid4(), compiled_hash=_hash(studio), status="concluida", driver="live", completa=True, aprovado=True,
        orcamento_excedido=False, total_casos=4, casos_aprovados=4))


def _cenario_sem_numero_fallback(studio):
    """Green in every other way, but nobody set the hand-off fallback number (074): an empty settings store."""
    _cenario_verde(studio)
    runtime_settings.install_runtime_settings_service(
        runtime_settings.RuntimeSettingsService(FakeRuntimeSettingsStore(), settings, ttl_seconds=0))


def _cenario_sem_catalogo(studio):
    """Green in every other way, but the generic offer tool is ACTIVE and no standard names a catalogue (081)."""
    _cenario_verde(studio)
    assert studio.put(f"{BASE}/novo/draft/ferramentas", json={"itens": [
        {"ferramenta": "oferecer_opcoes", "descricao": "Oferece opções do catálogo.", "parametros": {}}]}).status_code == 200
    _passar_juiz(studio)


def _cenario_padrao_ausente(studio):
    _cenario_verde(studio)
    studio.store.update_definicao(DEFAULT_ORG_ID, "novo", {"padrao_qualificacao": "padrao-sem-versao"})
    _passar_juiz(studio)


def _cenario_aviso_apenas(studio):
    """Everything advisory at once -- and the draft is still publishable."""
    _cenario_verde(studio)
    assert studio.put(f"{BASE}/novo/draft/ferramentas", json={"itens": [
        {"ferramenta": "handoff", "descricao": "Passa para uma pessoa.", "parametros": {}}]}).status_code == 200
    _passar_juiz(studio)


def _cenario_compile_bloqueado(studio):
    _preencher(studio)
    assert studio.put(f"{BASE}/novo/draft/sections", json={"secoes": [
        *SECOES["secoes"], {"chave": "vazia", "titulo": "Vazia", "ordem": 20, "conteudo": "", "ativo": True}]}).status_code == 200


#: (name, builder, the publish refusal the state earns -- ``None`` = it publishes)
CENARIOS = [
    ("vazio", _cenario_vazio, "conteudo_incompleto"),
    ("secao_ativa_vazia", _cenario_compile_bloqueado, "compile_blocked"),
    ("sem_caso_de_avaliacao", _cenario_sem_caso, "eval_required"),
    ("sem_execucao_do_juiz", _cenario_sem_execucao, "eval_required"),
    ("juiz_abaixo_do_limiar", _cenario_juiz_abaixo, "eval_required"),
    ("mecanismo_sem_execucao", _cenario_mecanismo_sem_execucao, "mecanismo_reprovado"),
    ("padrao_sem_versao_publicada", _cenario_padrao_ausente, "qualificacao_indisponivel"),
    ("sem_numero_fallback", _cenario_sem_numero_fallback, "numero_fallback_ausente"),
    ("oferecer_opcoes_sem_catalogo", _cenario_sem_catalogo, "catalogo_ausente"),
    ("verde", _cenario_verde, None),
    ("verde_so_com_mecanismo", _cenario_verde_so_com_mecanismo, None),
    ("somente_avisos", _cenario_aviso_apenas, None),
]


def test_the_scenarios_exercise_every_publish_refusal_a_blocking_item_can_name():
    assert {r for _, _, r in CENARIOS if r} == pr.RECUSAS_PUBLICACAO


class TestGateParity:
    @pytest.mark.parametrize("nome,montar,recusa", CENARIOS, ids=[c[0] for c in CENARIOS])
    def test_ready_exactly_when_publish_passes_and_the_refusal_is_the_one_a_blocking_item_names(self, plat, nome, montar, recusa):
        montar(plat)
        pronto = _get(plat).json()
        resp = plat.post(f"{BASE}/novo/draft/publish", json={})
        assert pronto["pronto_para_publicar"] is (recusa is None), pronto["itens"]
        assert (resp.status_code == 200) is (recusa is None), resp.text
        if recusa is None:
            return
        assert resp.status_code == 409 and resp.json()["code"] == recusa, resp.text
        # the blocking items of the readiness view name publish's own refusal ...
        nomeados = {i["recusa_publicacao"] for i in pronto["itens"] if i["severidade"] == "bloqueante"}
        assert recusa in nomeados and nomeados <= pr.RECUSAS_PUBLICACAO
        # ... and the 409 carries the SAME list the readiness view returns
        assert [(i["codigo"], i["severidade"]) for i in resp.json()["prontidao"]] == [
            (i["codigo"], i["severidade"]) for i in pronto["itens"]]

    def test_the_mechanism_refusal_is_reported_with_its_motivo_in_both_places(self, plat):
        _cenario_mecanismo_sem_execucao(plat)
        resp = plat.post(f"{BASE}/novo/draft/publish", json={"override_reason": "x" * 30})
        assert resp.status_code == 409 and resp.json()["code"] == "mecanismo_reprovado"
        item = next(i for i in resp.json()["prontidao"] if i["recusa_publicacao"] == "mecanismo_reprovado")
        assert item["detalhe"]["motivo"] == resp.json()["motivo"] == "sem_execucao"

    def test_a_publish_refusal_still_answers_when_the_readiness_read_fails(self, plat):
        class _Quebrado:
            def list_cases(self, *_a, **_k):
                raise RuntimeError("store fora do ar")

        plat.raw.app.dependency_overrides[get_eval_store_dep] = lambda: _Quebrado()
        _preencher(plat)
        resp = plat.post(f"{BASE}/novo/draft/publish", json={})
        assert resp.status_code == 409 and resp.json()["code"] == "eval_required" and resp.json()["prontidao"] is None


def test_no_suggested_action_shows_an_api_path():
    """A human never sees an HTTP verb + path: every action is a button (or names a tab) in the studio."""
    import inspect
    import re

    src = inspect.getsource(pr).split("from __future__", 1)[1]  # the module docstring is for developers
    assert not re.findall(r"\b(?:POST|PUT|PATCH|DELETE)\s+(?:\.\.\.|/api)", src)


# ── the canonical template's must-haves (owner 2026-11-08) ──────────────────


class TestModeloCanonico:
    def test_missing_must_haves_are_advisory_and_never_block_publish(self):
        p = pr.compor(_entrada(canonico_exigido=True, casos_comportamento=3, juiz=_juiz()))
        assert {"sem_secao_discordar", "sem_evals_bajulacao"} <= set(_codigos(p, "aviso"))
        assert p.pronto_para_publicar

    def test_both_present_is_ok(self):
        p = pr.compor(_entrada(canonico_exigido=True, regras_secoes=(pr.REGRA_DISCORDAR,),
                               tags_comportamento=(pr.TAG_BAJULACAO,), casos_comportamento=3, juiz=_juiz()))
        assert "modelo_canonico" in _codigos(p, "ok") and not {"sem_secao_discordar", "sem_evals_bajulacao"} & set(_codigos(p))

    def test_not_required_says_nothing(self):
        p = pr.compor(_entrada(casos_comportamento=3, juiz=_juiz()))
        assert not [i for i in p.itens if i.grupo == "modelo"]

    def test_the_route_reads_section_rules_and_case_tags(self, plat):
        assert {"sem_secao_discordar", "sem_evals_bajulacao"} <= {i["codigo"] for i in _get(plat).json()["itens"]}
        # The rule lives inside `honestidade`, not in a section named after it.
        secao = {"chave": "honestidade", "titulo": "Honestidade", "ordem": 10,
                 "conteudo": "Você discorda com respeito.", "ativo": True, "regras": [pr.REGRA_DISCORDAR]}
        assert plat.put(f"{BASE}/novo/draft/sections", json={"secoes": [secao]}).status_code == 200
        _caso(plat, slug="b1", tags=["bajulacao"])
        codigos = {i["codigo"] for i in _get(plat).json()["itens"]}
        assert "modelo_canonico" in codigos and "sem_secao_discordar" not in codigos

    def test_untagged_honestidade_and_the_old_key_do_not_pass(self, plat):
        """No fallback to the key: a section NAMED ``discordar-com-respeito`` without the rule fails; so does an
        untagged ``honestidade``."""
        secoes = [
            {"chave": "honestidade", "titulo": "Honestidade", "ordem": 10, "conteudo": "Você discorda com respeito.",
             "ativo": True},
            {"chave": "discordar-com-respeito", "titulo": "Discordar", "ordem": 20, "conteudo": "x", "ativo": True},
        ]
        assert plat.put(f"{BASE}/novo/draft/sections", json={"secoes": secoes}).status_code == 200
        assert "sem_secao_discordar" in {i["codigo"] for i in _get(plat).json()["itens"]}

    def test_a_blank_or_inactive_tagged_section_does_not_count(self, plat):
        base = {"chave": "honestidade", "titulo": "Honestidade", "ordem": 10, "regras": [pr.REGRA_DISCORDAR]}
        for extra in ({"conteudo": "   ", "ativo": True}, {"conteudo": "texto", "ativo": False}):
            assert plat.put(f"{BASE}/novo/draft/sections", json={"secoes": [{**base, **extra}]}).status_code == 200
            assert "sem_secao_discordar" in {i["codigo"] for i in _get(plat).json()["itens"]}

    def test_an_unknown_rule_is_refused_with_a_portuguese_422(self, plat):
        secao = {"chave": "honestidade", "titulo": "Honestidade", "ordem": 10, "conteudo": "x", "ativo": True,
                 "regras": ["inventada"]}
        r = plat.put(f"{BASE}/novo/draft/sections", json={"secoes": [secao]})
        assert r.status_code == 422
        assert "Regra de seção desconhecida" in str(r.json()) and "inventada" in str(r.json())


class TestGrupos:
    def test_an_item_outside_the_closed_group_set_is_refused(self, monkeypatch):
        monkeypatch.setattr(pr, "_canonico", lambda e: [pr.Item("x", "inventado", "aviso", "m")])
        with pytest.raises(ValueError, match="outside GRUPOS"):
            pr.compor(_entrada())

    def test_every_group_the_composer_emits_is_declared(self):
        import ast
        from pathlib import Path

        tree = ast.parse(Path(pr.__file__).read_text(encoding="utf-8"))
        emitidos = {n.args[1].value for n in ast.walk(tree)
                    if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "Item" and len(n.args) >= 2}
        assert emitidos <= set(pr.GRUPOS)

    def test_the_frontend_labels_exactly_the_backend_groups(self):
        import re
        from pathlib import Path

        ts = (Path(__file__).resolve().parents[4] / "frontend/src/api/studio/types-prontidao.ts").read_text(encoding="utf-8")
        union = ts.split("export type ProntidaoGrupo =", 1)[1].split(";", 1)[0]
        labels = ts.split("PRONTIDAO_GRUPO_LABEL", 1)[1].split("};", 1)[0]
        assert set(re.findall(r'"([a-z_]+)"', union)) == set(pr.GRUPOS)
        assert set(re.findall(r"^\s*([a-z_]+):", labels, re.M)) == set(pr.GRUPOS)


class TestNumeroFallback:
    def test_a_conversational_agent_without_the_number_is_blocked_and_with_it_is_ok(self):
        sem = pr.compor(_entrada(numero_fallback_definido=False, canonico_exigido=True))
        item = next(i for i in sem.itens if i.codigo == "numero_fallback_ausente")
        assert item.severidade == "bloqueante" and item.recusa_publicacao == "numero_fallback_ausente"
        com = pr.compor(_entrada(numero_fallback_definido=True, canonico_exigido=True))
        assert "numero_fallback_ausente" not in _codigos(com) and "numero_fallback_definido" in _codigos(com)

    def test_the_internal_generator_needs_no_number(self):
        assert "numero_fallback_ausente" not in _codigos(pr.compor(_entrada(numero_fallback_definido=False, canonico_exigido=False)))

