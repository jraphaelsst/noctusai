"""Golden-file tests of the pure engine against the CONTRACT §4.3 v1 shape
(fixture data; the real v1 is seeded as DB data, never from code)."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.qualificacao import engine
from app.qualificacao.models import EventoImovel, ParametrosDef, Registro
from tests.qualificacao.fixture_v1 import VERSAO_ID, _em, _preenchido, versao_v1

GOLDEN = json.loads((Path(__file__).parent / "golden" / "estagios_v1.json").read_text())
AGORA = datetime(2026, 10, 19, tzinfo=timezone.utc)


def _registros(d):
    return [Registro(criterio_chave=k, valor=v) for k, v in d.items()]


def _eventos(lst):
    return [EventoImovel(codigo_imovel=c, evento=e, origem="campanha") for e, c in lst]


@pytest.mark.parametrize("caso", GOLDEN, ids=[c["nome"] for c in GOLDEN])
def test_golden(caso):
    estado = engine.calcular(versao_v1(), _registros(caso["registros"]), _eventos(caso["eventos"]), AGORA)
    esp = caso["esperado"]
    assert estado.estagio == esp["estagio"]
    assert estado.score == esp["score"]
    assert list(estado.faltando) == esp["faltando"]
    assert (estado.proximo_criterio.chave if estado.proximo_criterio else None) == esp["proximo"]
    assert estado.pode_ofertar is esp["pode_ofertar"]
    assert estado.pode_concluir is esp["pode_concluir"]
    for k, v in esp.get("derivados", {}).items():
        assert estado.valores[k] == v
    assert estado.calculado_em == AGORA


def test_every_stage_is_reached_by_some_golden_case():
    v = versao_v1()
    alcancados = {c["esperado"]["estagio"] for c in GOLDEN}
    esperados = {e.chave for e in v.estagios if not e.terminal}
    assert esperados <= alcancados, esperados - alcancados


def test_terminal_stage_is_never_computed():
    v = versao_v1()
    cheio = {c["nome"]: c for c in GOLDEN}["qualificado_com_visita_e_pronto"]
    estado = engine.calcular(v, _registros(cheio["registros"]), _eventos(cheio["eventos"]))
    assert estado.estagio != "descartado"


def test_hash_is_stable_and_changes_with_state():
    v = versao_v1()
    a = engine.calcular(v, _registros({"operacao": "compra"}), [])
    b = engine.calcular(v, _registros({"operacao": "compra"}), [])
    c = engine.calcular(v, _registros({"operacao": "aluguel"}), [])
    assert a.hash == b.hash != c.hash


def test_later_record_wins():
    v = versao_v1()
    regs = [Registro("prazo_decisao", "6_12m"), Registro("prazo_decisao", "imediato")]
    assert engine.calcular(v, regs, []).valores["prazo_decisao"] == "imediato"


def test_record_the_version_no_longer_accepts_is_ignored():
    v = versao_v1()
    regs = [Registro("operacao", "compra"), Registro("operacao", "permuta_total")]
    # the invalid LATER record is skipped, the earlier valid one stays
    assert engine.calcular(v, regs, []).valores["operacao"] == "compra"


def test_unknown_inactive_and_nao_coletar_criteria_are_ignored():
    v = versao_v1()
    regs = [Registro("inexistente", "x"), Registro("profissao", "medica")]
    assert engine.calcular(v, regs, []).valores == {}
    inativo = replace(v, criterios=tuple(replace(c, ativo=False) if c.chave == "operacao" else c for c in v.criterios))
    assert "operacao" not in engine.calcular(inativo, [Registro("operacao", "compra")], []).valores


def test_derived_criteria_cannot_be_recorded():
    v = versao_v1()
    assert engine.calcular(v, [Registro("deseja_visitar", True)], []).valores == {}


def test_score_clamps_to_score_max_and_to_zero():
    v = versao_v1()
    baixo = replace(v, parametros=replace(v.parametros, score_max=20))
    cheio = {c["nome"]: c for c in GOLDEN}["qualificado_com_visita_e_pronto"]
    assert engine.calcular(baixo, _registros(cheio["registros"]), _eventos(cheio["eventos"])).score == 20
    negativo = _registros({"precisa_vender_atual": True, "bloqueios": ["aprovacao_credito", "venda_imovel"]})
    assert engine.calcular(v, negativo, []).score == 0


def test_no_stage_true_is_an_engine_error_not_a_silent_fallback():
    v = versao_v1()
    sem_base = replace(v, estagios=tuple(e for e in v.estagios if e.chave != "novo"))
    with pytest.raises(engine.EngineError):
        engine.calcular(sem_base, [], [])


def test_faltando_is_empty_at_the_top_stage_and_skips_terminal_next():
    v = versao_v1()
    topo = {c["nome"]: c for c in GOLDEN}["prazo_imediato_dispensa_visita"]
    e = engine.calcular(v, _registros(topo["registros"]), [])
    assert e.estagio == "pronto_para_corretor" and e.faltando == () and e.proximo_criterio is None


def test_proximo_criterio_carries_options_without_synonyms():
    e = engine.calcular(versao_v1(), [], [])
    d = e.avaliar_payload()["proximo_criterio"]
    assert d["chave"] == "operacao"
    assert d["opcoes"] == [
        {"valor": "compra", "rotulo": "Compra", "descricao_modelo": "significa compra"},
        {"valor": "aluguel", "rotulo": "Aluguel", "descricao_modelo": "significa aluguel"},
    ]
    assert set(e.avaliar_payload()) == {"estagio", "score", "faltando", "proximo_criterio", "pode_ofertar", "pode_concluir"}


# ── per-type scoring ────────────────────────────────────────────────────────

@pytest.mark.parametrize("chave,valor,pts", [
    ("operacao", "compra", 10),
    ("precisa_vender_atual", True, -5),
    ("precisa_vender_atual", False, 0),
    ("bloqueios", ["outro", "documentacao", "venda_imovel"], -9),
    ("faixa_preco", {"min": 1, "max": 3}, 10),
    ("quartos_min", 0, 0),
    ("quartos_min", 2, 3),
    ("caracteristicas", ["piscina", "varanda"], 2),
    ("caracteristicas", ["piscina", "varanda", "elevador", "portaria", "area_lazer", "churrasqueira"], 5),
    ("composicao_familiar", "casal e dois filhos", 2),
])
def test_pontuar_criterio_by_type(chave, valor, pts):
    c = versao_v1().criterio(chave)
    assert engine.pontuar_criterio(c, valor) == pts


# ── value validation ────────────────────────────────────────────────────────

@pytest.mark.parametrize("chave,valor,ok,codigo", [
    ("operacao", "compra", True, None),
    ("operacao", "troca", False, "opcao_invalida"),
    ("operacao", 3, False, "valor_invalido"),
    ("bloqueios", ["outro", "outro"], True, None),
    ("bloqueios", [], False, "valor_invalido"),
    ("bloqueios", ["x"], False, "opcao_invalida"),
    ("regioes", ["qualquer lugar livre"], True, None),
    ("regioes", "centro", False, "valor_invalido"),
    ("precisa_vender_atual", "sim", False, "valor_invalido"),
    ("quartos_min", True, False, "valor_invalido"),
    ("quartos_min", float("inf"), False, "valor_invalido"),
    ("faixa_preco", {"min": 5, "max": 1}, False, "valor_invalido"),
    ("faixa_preco", {"min": 5, "teto": 9}, False, "valor_invalido"),
    ("faixa_preco", {"max": 9}, True, None),
    ("nome", "   ", False, "valor_invalido"),
])
def test_validar_valor(chave, valor, ok, codigo):
    got_ok, _, got_codigo = engine.validar_valor(versao_v1().criterio(chave), valor)
    assert (got_ok, got_codigo) == (ok, codigo)


def test_validar_valor_normalises():
    c = versao_v1()
    assert engine.validar_valor(c.criterio("bloqueios"), ["outro", "outro", "documentacao"])[1] == ["outro", "documentacao"]
    assert engine.validar_valor(c.criterio("nome"), "  Ana ")[1] == "Ana"


# ── publish-time validation ─────────────────────────────────────────────────

def test_v1_fixture_publishes_clean():
    assert engine.validar_versao(versao_v1()) == []


def _codes(v):
    return {e["code"] for e in engine.validar_versao(v)}


def test_unknown_criterion_in_a_stage_rule_is_refused():
    v = versao_v1()
    ruim = replace(v.estagios[2], regra={"todos": [_preenchido("nao_existe")]})
    assert "criterio_desconhecido" in _codes(replace(v, estagios=(*v.estagios[:2], ruim, *v.estagios[3:])))


def test_unknown_op_and_unknown_event_are_refused():
    v = versao_v1()
    ruim = replace(v.estagios[2], regra={"criterio": "operacao", "op": "parecido"})
    assert "op_desconhecido" in _codes(replace(v, estagios=(*v.estagios[:2], ruim, *v.estagios[3:])))
    ruim = replace(v.estagios[2], regra={"evento": "casou"})
    assert "evento_desconhecido" in _codes(replace(v, estagios=(*v.estagios[:2], ruim, *v.estagios[3:])))


def test_unknown_criterion_in_minimo_para_ofertar_is_refused():
    v = versao_v1()
    assert "criterio_desconhecido" in _codes(replace(v, parametros=ParametrosDef({"criterio": "x", "op": "preenchido"})))


def test_no_always_matching_base_stage_is_refused():
    v = versao_v1()
    sem_base = replace(v.estagios[0], regra=_preenchido("operacao"))
    assert "sem_estagio_base" in _codes(replace(v, estagios=(sem_base, *v.estagios[1:])))


@pytest.mark.parametrize("base", [
    {"todos": []}, {"score": {">=": 0}}, {"nao": {"algum": []}}, {"algum": [{"todos": []}, _preenchido("operacao")]},
])
def test_accepted_always_true_bases(base):
    v = versao_v1()
    assert "sem_estagio_base" not in _codes(replace(v, estagios=(replace(v.estagios[0], regra=base), *v.estagios[1:])))


@pytest.mark.parametrize("base", [{"algum": []}, {"score": {">=": 1}}, {"nao": {"todos": []}}])
def test_rejected_non_always_bases(base):
    v = versao_v1()
    assert "sem_estagio_base" in _codes(replace(v, estagios=(replace(v.estagios[0], regra=base), *v.estagios[1:])))


def test_too_deep_rule_is_refused_like_a_cycle():
    regra: dict = {"todos": []}
    for _ in range(14):
        regra = {"nao": {"nao": regra}}
    v = versao_v1()
    assert "regra_profunda" in _codes(replace(v, estagios=(replace(v.estagios[0], regra=regra), *v.estagios[1:])))


def test_structural_errors():
    v = versao_v1()
    dup = replace(v, criterios=(*v.criterios, v.criterios[0]))
    assert "criterio_duplicado" in _codes(dup)
    enum_sem_opcoes = replace(v, criterios=(replace(v.criterios[0], opcoes=()), *v.criterios[1:]))
    assert "opcoes_obrigatorias" in _codes(enum_sem_opcoes)
    assert "sem_estagios" in _codes(replace(v, estagios=()))
    ordem_dup = replace(v, estagios=(v.estagios[0], replace(v.estagios[1], ordem=0), *v.estagios[2:]))
    assert "ordem_duplicada" in _codes(ordem_dup)
    assert "parametro_invalido" in _codes(replace(v, parametros=replace(v.parametros, lote_ofertas=9)))
    pont = replace(v.criterios[0], pontuacao={"opcoes": {"fantasma": 3}})
    assert "pontuacao_invalida" in _codes(replace(v, criterios=(pont, *v.criterios[1:])))
    sens = replace(v.criterios[0], sensivel="faixa", tipo="bool", opcoes=())
    assert "sensivel_invalido" in _codes(replace(v, criterios=(sens, *v.criterios[1:])))
