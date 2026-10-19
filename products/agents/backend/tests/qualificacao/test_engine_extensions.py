"""Data-driven extensions (tech-lead 2026-10-19): score AXES, negative points and
disqualifying options (a terminal stage reached by rule), per-criterion validity
(`validade_dias`). All content here is FIXTURE data layered on the v1 shape."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.qualificacao import engine
from app.qualificacao.models import CriterioDef, EstagioDef, EventoImovel, LeadSinais, Opcao, Registro
from app.qualificacao.regras import Contexto, avaliar_regra
from tests.qualificacao.fixture_v1 import _em, _preenchido, versao_v1

AGORA = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


def _com_eixos(v):
    eixos = {"operacao": "fit", "tipo_imovel": "fit", "faixa_preco": "fit", "prazo_decisao": "intencao",
             "forma_pagamento": "intencao", "precisa_vender_atual": "intencao"}
    return replace(v, criterios=tuple(replace(c, eixo=eixos.get(c.chave)) for c in v.criterios))


def _reg(**kv):
    return [Registro(k, val) for k, val in kv.items()]


def test_axes_are_scored_separately_and_the_total_still_counts_everything():
    v = _com_eixos(versao_v1())
    e = engine.calcular(v, _reg(operacao="compra", tipo_imovel="casa", prazo_decisao="imediato",
                                forma_pagamento="a_vista", regioes=["centro"]), [], AGORA)
    assert e.scores == {"fit": 15, "intencao": 40}
    assert e.score == 15 + 40 + 8  # regioes has no axis: total only
    assert e.avaliar_payload()["scores"] == {"fit": 15, "intencao": 40}


def test_an_axis_without_points_is_zero_and_no_axes_means_no_scores_key():
    e = engine.calcular(_com_eixos(versao_v1()), [], [], AGORA)
    assert e.scores == {"fit": 0, "intencao": 0}
    assert "scores" not in engine.calcular(versao_v1(), [], [], AGORA).avaliar_payload()


def test_axis_is_clamped_independently():
    v = _com_eixos(versao_v1())
    v = replace(v, parametros=replace(v.parametros, score_max=30))
    e = engine.calcular(v, _reg(prazo_decisao="imediato", forma_pagamento="a_vista"), [], AGORA)
    assert e.scores["intencao"] == 30 and e.score == 30


def test_stage_rule_on_an_axis_score():
    v = _com_eixos(versao_v1())
    quente = EstagioDef("intencao_alta", "Intencao alta", 5, {"score": {"eixo": "intencao", ">=": 30}})
    v = replace(v, estagios=(*[e for e in v.estagios if e.chave != "pronto_para_corretor"], quente))
    assert engine.validar_versao(v) == []
    base = _reg(operacao="compra", prazo_decisao="ate_3m")
    assert engine.calcular(v, base, [], AGORA).estagio != "intencao_alta"  # intencao 20
    assert engine.calcular(v, base + _reg(forma_pagamento="financiamento"), [], AGORA).estagio == "intencao_alta"


def test_axis_atom_evaluates_and_unknown_axis_is_refused_at_publish():
    ctx = Contexto({}, 10, frozenset(), {"fit": 7})
    assert avaliar_regra({"score": {"eixo": "fit", ">=": 7}}, ctx) is True
    assert avaliar_regra({"score": {"eixo": "fit", ">=": 8}}, ctx) is False
    assert avaliar_regra({"score": {"eixo": "outro", ">=": 1}}, ctx) is False
    v = _com_eixos(versao_v1())
    ruim = replace(v.estagios[2], regra={"score": {"eixo": "fantasma", ">=": 1}})
    erros = engine.validar_versao(replace(v, estagios=(*v.estagios[:2], ruim, *v.estagios[3:])))
    assert "eixo_desconhecido" in {x["code"] for x in erros}


def test_disqualifying_option_only_SUGGESTS_the_terminal_stage_until_a_human_confirms():
    v = versao_v1()
    inv = replace(v.criterios[0], chave="motivo_descarte", opcoes=(Opcao("sem_interesse"), Opcao("invalido")),
                  pontuacao={"opcoes": {"invalido": -50}}, ordem=999, grupo="bloqueios")
    descartado = EstagioDef("descartado", "Descartado", 6,
                            {"id": "descarte.R1", **_em("motivo_descarte", "sem_interesse", "invalido")}, terminal=True)
    v = replace(v, criterios=(*v.criterios, inv),
                estagios=(*[e for e in v.estagios if e.chave != "descartado"], descartado))
    assert engine.validar_versao(v) == []
    qualificado = _reg(operacao="compra", tipo_imovel="casa", faixa_preco={"max": 4}, regioes=["a"],
                       prazo_decisao="imediato", forma_pagamento="a_vista")
    assert engine.calcular(v, qualificado, [], AGORA).descartado_sugerido is None
    e = engine.calcular(v, qualificado + _reg(motivo_descarte="invalido"), [], AGORA)
    assert e.estagio == "pronto_para_corretor"  # NOT descartado: the machine never decides it
    assert e.descartado_sugerido == {"estagio": "descartado", "regra_id": "descarte.R1"}
    assert e.avaliar_payload()["descartado_sugerido"]["estagio"] == "descartado"
    assert e.score == 73 - 50
    c = engine.calcular(v, qualificado + _reg(motivo_descarte="invalido"), [], AGORA, confirmados=["descartado"])
    assert c.estagio == "descartado" and c.descartado_sugerido is None and c.faltando == () and not c.pode_concluir
    # a confirmation does nothing once the rule is no longer true
    assert engine.calcular(v, qualificado, [], AGORA, confirmados=["descartado"]).estagio == "pronto_para_corretor"


def test_validade_dias_expires_a_record_and_the_criterion_is_missing_again():
    v = versao_v1()
    v = replace(v, criterios=tuple(replace(c, validade_dias=30) if c.chave == "prazo_decisao" else c for c in v.criterios))
    velho = Registro("prazo_decisao", "imediato", created_at=AGORA - timedelta(days=31))
    novo = Registro("prazo_decisao", "imediato", created_at=AGORA - timedelta(days=29))
    sem_validade = Registro("operacao", "compra", created_at=AGORA - timedelta(days=900))
    e = engine.calcular(v, [velho, sem_validade], [], AGORA)
    assert "prazo_decisao" not in e.valores and e.valores["operacao"] == "compra"
    assert engine.calcular(v, [novo], [], AGORA).valores["prazo_decisao"] == "imediato"


def test_expired_criterion_returns_to_faltando():
    v = versao_v1()
    v = replace(v, criterios=tuple(replace(c, validade_dias=10) if c.chave == "operacao" else c for c in v.criterios))
    regs = [Registro("operacao", "compra", created_at=AGORA - timedelta(days=11))]
    e = engine.calcular(v, regs, [], AGORA)
    assert e.estagio == "novo" and e.faltando[0] == "operacao"


def test_no_clock_means_nothing_expires():
    v = versao_v1()
    v = replace(v, criterios=tuple(replace(c, validade_dias=1) if c.chave == "operacao" else c for c in v.criterios))
    regs = [Registro("operacao", "compra", created_at=AGORA - timedelta(days=500))]
    assert engine.calcular(v, regs, [], None).valores["operacao"] == "compra"


def test_invalid_axis_and_validity_are_refused_at_publish():
    v = versao_v1()
    ruim = replace(v.criterios[0], eixo="Fit Total", validade_dias=0)
    codes = {x["code"] for x in engine.validar_versao(replace(v, criterios=(ruim, *v.criterios[1:])))}
    assert {"eixo_invalido", "validade_invalida"} <= codes


def test_service_applies_validity_with_its_clock_and_persists_scores():
    from app.qualificacao.lead_store import FakeLeadQualificacaoStore
    from app.qualificacao.service import ItemPerfil, QualificacaoService
    from app.qualificacao.store import FakePadraoStore
    from tests.qualificacao.harness import AGENTE, LEAD, ORG, preencher_rascunho

    padroes = FakePadraoStore()
    p = padroes.criar_padrao("imob-lead", "I", None)
    vid = padroes.criar_rascunho(p.id, None, None)
    preencher_rascunho(padroes, vid)
    ope = padroes.obter_versao(vid).criterio("operacao")
    padroes.salvar_criterio(vid, replace(ope, eixo="fit", validade_dias=30))
    padroes.publicar(vid, AGENTE)
    relogio = [AGORA]
    leads = FakeLeadQualificacaoStore()
    svc = QualificacaoService(padroes, leads, agora=lambda: relogio[0])
    # records are stamped by the store with the real now; age them through the clock instead
    r = svc.registrar_perfil(ORG, LEAD, agent_id=AGENTE, versao_id=vid,
                             itens=[ItemPerfil("operacao", "compra", "comprar")], mensagens_lead=["comprar"])
    assert r.estado.scores == {"fit": 10}
    assert leads.obter_estado(ORG, LEAD).scores == {"fit": 10}
    relogio[0] = datetime.now(timezone.utc) + timedelta(days=31)
    e = svc.avaliar(ORG, LEAD, vid)
    assert "operacao" not in e.valores and e.scores == {"fit": 0}


# ── scopes: one agent never asks another agent's questions ──────────────────

def _com_escopos(v):
    fin = {"forma_pagamento", "credito_aprovado", "bloqueios", "precisa_vender_atual"}
    return replace(v, criterios=tuple(replace(c, escopo="financeiro") if c.chave in fin else replace(c, escopo="sdr") if c.chave in ("operacao", "tipo_imovel", "faixa_preco", "regioes", "prazo_decisao") else c for c in v.criterios))


def test_faltando_and_proximo_only_offer_the_asking_scope():
    v = _com_escopos(versao_v1())
    base = _reg(operacao="compra", tipo_imovel="casa", faixa_preco={"max": 4}, regioes=["a"], prazo_decisao="ate_3m")
    sdr = engine.calcular(v, base, [], AGORA, "sdr")
    fin = engine.calcular(v, base, [], AGORA, "financeiro")
    todos = engine.calcular(v, base, [], AGORA)
    assert sdr.faltando == () and sdr.proximo_criterio is None  # bloqueios is financeiro's
    assert fin.faltando == ("bloqueios",) and fin.proximo_criterio.chave == "bloqueios"
    assert todos.faltando == ("bloqueios",)
    # state is the lead's shared state: the same stage and score for everyone
    assert (sdr.estagio, sdr.score, sdr.valores) == (fin.estagio, fin.score, fin.valores)


def test_unscoped_criterion_is_askable_by_every_scope():
    v = _com_escopos(versao_v1())
    assert engine.no_escopo(v.criterio("nome"), "sdr") and engine.no_escopo(v.criterio("nome"), "juridico")
    assert not engine.no_escopo(v.criterio("credito_aprovado"), "sdr")


def test_service_refuses_recording_outside_the_scope_but_shared_records_are_visible():
    from app.qualificacao.service import ItemPerfil
    from tests.qualificacao.harness import AGENTE, LEAD, ORG, montar_servico

    svc, padroes, leads, vid = montar_servico()
    # re-publish a scoped copy
    p = padroes.obter_padrao("imob-lead")
    novo = padroes.criar_rascunho(p.id, None, vid)
    for c in _com_escopos(versao_v1()).criterios:
        padroes.salvar_criterio(novo, c)
    padroes.publicar(novo, AGENTE)
    r = svc.registrar_perfil(ORG, LEAD, agent_id=AGENTE, versao_id=novo, escopo="sdr", mensagens_lead=["pago a vista"],
                             itens=[ItemPerfil("forma_pagamento", "a_vista", "a vista")])
    assert [x.codigo for x in r.recusados] == ["fora_do_escopo"]
    r = svc.registrar_perfil(ORG, LEAD, agent_id=AGENTE, versao_id=novo, escopo="financeiro", mensagens_lead=["pago a vista"],
                             itens=[ItemPerfil("forma_pagamento", "a_vista", "a vista")])
    assert r.ok
    # the SDR scope sees the value the financeiro agent recorded (shared lead)
    assert svc.avaliar(ORG, LEAD, novo, "sdr").valores["forma_pagamento"] == "a_vista"


# ── 1. axes: multipliers ────────────────────────────────────────────────────

def _com_params(v, **eixos):
    return replace(v, parametros=replace(v.parametros, eixos=eixos))


def test_axis_multiplier_applies_when_its_rule_is_true_and_is_data():
    v = _com_params(_com_eixos(versao_v1()), intencao={"multiplicadores": [
        {"quando": _preenchido("bloqueios"), "fator": 0.6}]})
    assert engine.validar_versao(v) == []
    base = _reg(prazo_decisao="imediato", forma_pagamento="a_vista")  # intencao 40
    sem = engine.calcular(v, base, [], AGORA)
    com = engine.calcular(v, base + _reg(bloqueios=["outro"]), [], AGORA)
    assert sem.scores["intencao"] == 40
    assert com.scores["intencao"] == round(40 * 0.6)
    assert com.detalhe["eixos"]["intencao"]["multiplicador"] == 0.6 and com.detalhe["eixos"]["intencao"]["bruto"] == 40


def test_axis_max_is_configurable_and_a_declared_axis_without_criteria_is_zero():
    v = _com_params(_com_eixos(versao_v1()), intencao={"max": 25}, urgencia={})
    e = engine.calcular(v, _reg(prazo_decisao="imediato", forma_pagamento="a_vista"), [], AGORA)
    assert e.scores["intencao"] == 25 and e.scores["urgencia"] == 0


def test_axis_config_is_validated_at_publish():
    v = _com_eixos(versao_v1())
    def codes(**eixos):
        return {x["code"] for x in engine.validar_versao(_com_params(v, **eixos))}
    assert "multiplicador_invalido" in codes(intencao={"multiplicadores": [{"quando": {"score": {">=": 1}}, "fator": 0.5}]})
    assert "multiplicador_invalido" in codes(intencao={"multiplicadores": [{"quando": {"todos": []}, "fator": -1}]})
    assert "criterio_desconhecido" in codes(intencao={"multiplicadores": [{"quando": _preenchido("x"), "fator": 1}]})
    assert "decaimento_invalido" in codes(intencao={"decaimento": [{"apos_dias": 30, "fator": 0.5}, {"apos_dias": 14, "fator": 0.7}]})
    assert "decaimento_invalido" in codes(intencao={"decaimento": [{"apos_dias": 14, "fator": 1.5}]})
    assert "eixo_invalido" in codes(Maiuscula={})


# ── 2. decay per axis, from the last lead reply ─────────────────────────────

DECAI = {"intencao": {"decaimento": [{"apos_dias": 14, "fator": 0.75}, {"apos_dias": 30, "fator": 0.5}]}}


@pytest.mark.parametrize("dias,esperado", [(0, 40), (13, 40), (14, 30), (29, 30), (30, 20), (90, 20)])
def test_intencao_decays_by_data_fit_never_does(dias, esperado):
    v = _com_params(_com_eixos(versao_v1()), **DECAI)
    sinais = LeadSinais(ultima_resposta_em=AGORA - timedelta(days=dias, minutes=1))
    e = engine.calcular(v, _reg(operacao="compra", prazo_decisao="imediato", forma_pagamento="a_vista"), [], AGORA, sinais=sinais)
    assert e.scores["intencao"] == esperado
    assert e.scores["fit"] == 10
    assert e.detalhe["eixos"]["fit"]["decaimento"] == 1.0


def test_no_reply_time_means_no_decay_and_days_are_derived():
    v = _com_params(_com_eixos(versao_v1()), **DECAI)
    regs = _reg(prazo_decisao="imediato", forma_pagamento="a_vista")
    assert engine.calcular(v, regs, [], AGORA).scores["intencao"] == 40
    e = engine.calcular(v, regs, [], AGORA, sinais=LeadSinais(AGORA - timedelta(days=20), 7))
    assert e.valores["dias_sem_resposta"] == 20 and e.valores["respostas_count"] == 7


# ── 3. system-derived criteria are not recordable ───────────────────────────

def test_derived_criteria_are_refused_by_registrar_perfil_and_come_from_signals():
    from app.qualificacao.service import ItemPerfil
    from tests.qualificacao.harness import AGENTE, LEAD, ORG, montar_servico

    svc, padroes, _, vid = montar_servico()
    p = padroes.obter_padrao("imob-lead")
    novo = padroes.criar_rascunho(p.id, None, vid)
    base = versao_v1().criterios[0]
    padroes.salvar_criterio(novo, replace(base, chave="respostas_count", tipo="derivado", opcoes=(), pontuacao=[{"min": 3, "pts": 4}], ordem=900))
    padroes.salvar_criterio(novo, replace(base, chave="dias_sem_resposta", tipo="derivado", opcoes=(), pontuacao={}, ordem=901))
    padroes.publicar(novo, AGENTE)
    r = svc.registrar_perfil(ORG, LEAD, agent_id=AGENTE, versao_id=novo, mensagens_lead=["tres respostas"], itens=[
        ItemPerfil("respostas_count", 5, "tres"), ItemPerfil("dias_sem_resposta", 0, "tres")])
    assert {(x.criterio, x.codigo) for x in r.recusados} == {
        ("respostas_count", "criterio_derivado"), ("dias_sem_resposta", "criterio_derivado")}
    e = svc.avaliar(ORG, LEAD, novo, sinais=LeadSinais(AGORA, 5))
    assert e.valores["respostas_count"] == 5 and e.score == 4  # the derived value scores through its bands


def test_derived_criterion_needs_a_system_source():
    v = versao_v1()
    ruim = replace(v.criterios[0], chave="inventado", tipo="derivado", opcoes=(), pontuacao={})
    assert "derivado_desconhecido" in {x["code"] for x in engine.validar_versao(replace(v, criterios=(*v.criterios, ruim)))}


def test_rejected_property_count_is_derived():
    from app.qualificacao.models import EventoImovel as EI
    ev = [EI("A", "oferecido", lote=1), EI("B", "oferecido", lote=1), EI("A", "nao_gostou"), EI("B", "descartado")]
    assert engine.valores_derivados(ev)["imoveis_rejeitados"] == 2


# ── 4. nurture stage, suggested discard, event override triggers ────────────

def test_nutrir_replaces_qualificado_frio_and_is_plain_data():
    v = versao_v1()
    estagios = tuple(replace(e, chave="nutrir", rotulo="Nutrir") if e.chave == "qualificado_frio" else e for e in v.estagios)
    v = replace(v, estagios=estagios)
    assert engine.validar_versao(v) == []
    e = engine.calcular(v, _reg(operacao="compra", tipo_imovel="casa", faixa_preco={"max": 4}, regioes=["a"], prazo_decisao="mais_12m"), [], AGORA)
    assert e.estagio == "nutrir"


def test_override_triggers_from_events_pediu_humano_and_two_rejected_lotes():
    v = versao_v1()
    escalar = EstagioDef("escalar", "Escalar para humano", 7, {"id": "escalar.R1", "algum": [
        {"id": "escalar.humano", "evento": "pediu_humano"},
        {"id": "escalar.lotes", "contagem": {"evento": "lote_rejeitado", ">=": 2}}]}, terminal=True)
    v = replace(v, estagios=(*v.estagios, escalar))
    assert engine.validar_versao(v) == []
    assert engine.calcular(v, [], [], AGORA).descartado_sugerido is None
    e = engine.calcular(v, [], [], AGORA, sinais=LeadSinais(eventos={"pediu_humano": 1}))
    assert e.descartado_sugerido == {"estagio": "escalar", "regra_id": "escalar.humano"}
    ev = [EventoImovel("A", "oferecido", lote=1), EventoImovel("B", "oferecido", lote=2),
          EventoImovel("A", "nao_gostou"), EventoImovel("B", "nao_gostou")]
    assert engine.contagens_de_eventos(ev)["lote_rejeitado"] == 2
    assert engine.calcular(v, [], ev, AGORA).descartado_sugerido["regra_id"] == "escalar.lotes"
    um = ev[:3]
    assert engine.calcular(v, [], um, AGORA).descartado_sugerido is None  # lote 2 not rejected yet


def test_event_atoms_are_validated():
    v = versao_v1()
    for regra in ({"evento": "casou"}, {"contagem": {"evento": "casou", ">=": 1}}, {"contagem": {"evento": "gostou"}}):
        ruim = replace(v.estagios[2], regra=regra)
        assert engine.validar_versao(replace(v, estagios=(*v.estagios[:2], ruim, *v.estagios[3:])))


# ── 5. explainability ───────────────────────────────────────────────────────

def test_regra_id_names_the_branch_that_fired_and_detalhe_breaks_points_down():
    v = _com_eixos(versao_v1())
    pronto = next(e for e in v.estagios if e.chave == "pronto_para_corretor")
    pronto = replace(pronto, regra={"id": "pronto", "todos": [
        {"id": "pronto.qualificado", **pronto.regra["todos"][0]},
        {"algum": [{"id": "pronto.R1", **_preenchido("deseja_visitar")}, {"id": "pronto.R2", **_em("prazo_decisao", "imediato")}]},
    ]})
    v = replace(v, estagios=tuple(pronto if e.chave == "pronto_para_corretor" else e for e in v.estagios))
    assert engine.validar_versao(v) == []
    regs = _reg(operacao="compra", tipo_imovel="casa", faixa_preco={"max": 4}, regioes=["a"], prazo_decisao="imediato", forma_pagamento="a_vista")
    e = engine.calcular(v, regs, [], AGORA)
    assert e.estagio == "pronto_para_corretor" and e.regra_id == "pronto"
    assert e.detalhe["eixos"]["fit"]["pontos"] == {"operacao": 10, "tipo_imovel": 5, "faixa_preco": 10}
    assert e.detalhe["eixos"]["intencao"]["pontos"] == {"prazo_decisao": 25, "forma_pagamento": 15}
    assert e.detalhe["sem_eixo"] == {"regioes": 8}


def test_regra_id_defaults_to_the_stage_key_and_follows_the_first_true_algum_branch():
    v = versao_v1()
    assert engine.calcular(v, [], [], AGORA).regra_id == "novo"
    estagio = EstagioDef("quente", "Quente", 8, {"algum": [
        {"id": "quente.A", "criterio": "deseja_visitar", "op": "preenchido"},
        {"id": "quente.B", "criterio": "operacao", "op": "preenchido"}]})
    v = replace(v, estagios=(*v.estagios, estagio))
    assert engine.calcular(v, _reg(operacao="compra"), [], AGORA).regra_id == "quente.B"


def test_rule_ids_must_be_short_text():
    v = versao_v1()
    ruim = replace(v.estagios[2], regra={"id": 7, "todos": []})
    assert "regra_invalida" in {x["code"] for x in engine.validar_versao(replace(v, estagios=(*v.estagios[:2], ruim, *v.estagios[3:])))}
