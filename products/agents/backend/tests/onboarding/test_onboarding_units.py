"""Checklist, importer and apply units (pure; no HTTP)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

import pytest

from app.onboarding.aplicar import aplicar, progresso
from app.onboarding.checklist import CHECKLIST, ordem_entrevista
from app.onboarding.importar import importar
from app.onboarding.sw_settings import FakeSwSettings
from app.studio.models import ConfigValidacao

ROOT = Path(__file__).resolve().parents[3]
DECL = {i["chave"]: i.get("tipo") for i in json.loads((ROOT / "projects/julia-v2/content-v3/julia-v3-specs.json").read_text())["itens"]}
#: keys typed by migration 059 (their JSON rows carry no tipo)
_059 = {"cnpj_oficial": "cnpj", "creci_j": "creci", "dominios_permitidos": "dominios", "aviso_privacidade_url": "url",
        "horario_atendimento": "horario", "prazo_retorno_humano": "duracao", "regioes_atendidas": "lista",
        "regioes_adjacentes": "lista", "contatos_oficiais": "contatos", "nome_imobiliaria": "texto_curto"}
TODAS = {c: DECL.get(c) or _059.get(c, "texto_longo") for c in {i.destino.alvo for i in CHECKLIST if i.destino.kind == "spec"}}


def test_checklist_has_41_items_17r_3c_and_every_optional_has_a_default_or_is_a_plain_choice():
    assert [i.n for i in CHECKLIST] == list(range(1, 42))
    assert sum(i.nivel == "R" for i in CHECKLIST) == 16 and sum(i.nivel == "C" for i in CHECKLIST) == 3
    assert all(i.quando for i in CHECKLIST if i.nivel == "C")


def test_every_spec_destination_is_declared_by_the_committed_julia_specs():
    # nome_imobiliaria + the migration-059 keys were declared on the live Julia definition before this JSON existed
    faltam = {i.destino.alvo for i in CHECKLIST if i.destino.kind == "spec"} - set(DECL) - set(_059)
    assert not faltam, f"declare in julia-v3-specs.json: {sorted(faltam)}"


def test_the_markdown_table_matches_the_code():
    md = (ROOT / "projects/onboarding/CHECKLIST.md").read_text()
    linhas: dict = {}
    for m in re.finditer(r"^\| (\d+) \| ([RCO]) \| .* \| (\w+) `(\w+)` \|$", md, re.M):
        linhas[int(m.group(1))] = (m.group(2), m.group(3), m.group(4))
    assert set(linhas) == {i.n for i in CHECKLIST}
    for i in CHECKLIST:
        assert linhas[i.n] == (i.nivel, i.destino.kind, i.destino.alvo), i.n


def test_interview_order_is_operations_then_required_then_conditional_then_optional():
    ordem = ordem_entrevista({"compra"})
    assert ordem[0].n == 9
    niveis = [i.nivel for i in ordem[1:]]
    assert niveis == sorted(niveis, key="RCO".index)
    assert 32 not in [i.n for i in ordem] and 28 in [i.n for i in ordem]
    assert {i.n for i in ordem_entrevista(None)} == set(range(1, 42))


def test_importer_maps_by_number_title_key_and_names_conflicts_and_leftovers():
    r = importar("1: Acme\nCNPJ: 11.222.333/0001-81\nconhecimento_venda: x\nlinha sem dois pontos\n3: outro")
    assert [(x.n, x.confirmado) for x in r.preenchidas] == [(1, False)]
    assert r.conflitos == ["item 3: valores diferentes na importação"]
    assert "linha sem dois pontos" in r.nao_reconhecidas and "conhecimento_venda: x" in r.nao_reconhecidas
    j = importar(json.dumps({"operacoes_atendidas": "compra", "37": {"lembrete_min": 15}}))
    assert [x.n for x in j.preenchidas] == [9, 37]
    with pytest.raises(ValueError):
        importar("x" * 70_000)


def _run(respostas, armazenados=None, sw=None, gravar=None):
    gravados: dict = {}
    rel = aplicar(
        respostas, org_id=uuid4(), declaradas=TODAS, armazenados=armazenados or {}, config=ConfigValidacao(modo="report"),
        gravar_specs=gravar or gravados.update, sw=sw or FakeSwSettings(),
    )
    return rel, gravados


def test_shared_knowledge_key_gets_labelled_lines_and_keeps_what_is_stored():
    rel, g = _run({9: "compra", 28: "Caixa e Itaú", 29: "ITBI 3%"}, {"conhecimento_venda": "Já existente"})
    assert g["conhecimento_venda"] == "Já existente\nFinanciamento: Caixa e Itaú\nCustos da compra: ITBI 3%"
    assert rel.aplicados == 3 and not rel.recusados


def test_a_write_path_error_is_reported_per_item_not_swallowed():
    def boom(_):
        raise RuntimeError("422 spec")

    rel, _ = _run({1: "Acme"}, gravar=boom)
    assert rel.itens[0].estado == "recusado" and rel.itens[0].codigo == "gravacao_recusada"


def test_too_many_extra_questions_is_refused():
    rel, g = _run({17: "a, b, c, d, e, f"})
    assert rel.itens[0].codigo == "valor_invalido" and g == {}


def test_progress_counts_required_and_conditional_that_apply():
    p = progresso({"locacao"}, {1: "x", 32: "y"})
    assert 1 not in p["faltando_obrigatorios"] and 32 not in p["faltando_obrigatorios"] and 28 not in p["faltando_obrigatorios"]
    assert p["por_nivel"]["R"]["feitos"] == 1
