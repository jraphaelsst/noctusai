"""Data-driven extensions (tech-lead 2026-10-19): score AXES, negative points and
disqualifying options (a terminal stage reached by rule), per-criterion validity
(`validade_dias`). All content here is FIXTURE data layered on the v1 shape."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.qualificacao import engine
from app.qualificacao.models import CriterioDef, EstagioDef, Opcao, Registro
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


def test_disqualifying_option_reaches_the_terminal_stage_by_rule_and_wins():
    v = versao_v1()
    inv = replace(v.criterios[0], chave="motivo_descarte", opcoes=(Opcao("sem_interesse"), Opcao("invalido")),
                  pontuacao={"opcoes": {"invalido": -50}}, ordem=999, grupo="bloqueios")
    descartado = EstagioDef("descartado", "Descartado", 6, _em("motivo_descarte", "sem_interesse", "invalido"), terminal=True)
    v = replace(v, criterios=(*v.criterios, inv),
                estagios=(*[e for e in v.estagios if e.chave != "descartado"], descartado))
    assert engine.validar_versao(v) == []
    qualificado = _reg(operacao="compra", tipo_imovel="casa", faixa_preco={"max": 4}, regioes=["a"],
                       prazo_decisao="imediato", forma_pagamento="a_vista")
    assert engine.calcular(v, qualificado, [], AGORA).estagio == "pronto_para_corretor"
    e = engine.calcular(v, qualificado + _reg(motivo_descarte="invalido"), [], AGORA)
    assert e.estagio == "descartado" and e.faltando == () and not e.pode_concluir
    assert e.score == 73 - 50


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
