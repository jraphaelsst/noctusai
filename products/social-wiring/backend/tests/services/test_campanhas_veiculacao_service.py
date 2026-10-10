"""Campanhas CRUD service — sw-lead-to-contract CONTRACT §1.1."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.campanhas_veiculacao_service import (
    CampanhaNaoEncontrada,
    CampanhasVeiculacaoService,
    CodigosDesconhecidos,
    VeiculacaoEmUso,
    VeiculacaoInvalida,
)
from tests.support.campanhas_fake import FakeCampanhasClient

ORG = uuid4()
OTHER = uuid4()


def _v(nivel, ref):
    return {"canal": "meta_ads", "nivel": nivel, "ref_codigo": ref}


@pytest.fixture
def env():
    c = FakeCampanhasClient()
    c.add_imovel(ORG, "ONE1", "Casa Um")
    c.add_imovel(ORG, "ONE2")
    c.add_imovel(OTHER, "ONE3")
    return c, CampanhasVeiculacaoService(c)


def test_criar_and_listar(env):
    _c, svc = env
    out = svc.criar(ORG, nome="Lançamento", imovel_codigos=["one1", "ONE2"],
                    veiculacoes=[_v("ad", "111"), _v("form", "222")])
    assert out["nome"] == "Lançamento"
    assert [i["codigo"] for i in out["imoveis"]] == ["ONE1", "ONE2"]
    assert out["imoveis"][0]["titulo"] == "Casa Um" and out["imoveis"][1]["titulo"] == "ONE2"
    assert {(v["nivel"], v["ref_codigo"]) for v in out["veiculacoes"]} == {("ad", "111"), ("form", "222")}
    assert [c["id"] for c in svc.listar(ORG)] == [out["id"]]
    assert svc.listar(OTHER) == []


def test_unknown_codigos_reported_and_nothing_created(env):
    c, svc = env
    with pytest.raises(CodigosDesconhecidos) as e:
        svc.criar(ORG, nome="x", imovel_codigos=["ONE1", "NOPE", "ONE3"], veiculacoes=[])
    assert e.value.codigos == ["NOPE", "ONE3"]  # ONE3 belongs to another org
    assert c.tables.get("campanhas", []) == []


def test_duplicate_ref_names_the_other_campanha(env):
    _c, svc = env
    svc.criar(ORG, nome="A", imovel_codigos=[], veiculacoes=[_v("ad", "111")])
    with pytest.raises(VeiculacaoEmUso) as e:
        svc.criar(ORG, nome="B", imovel_codigos=[], veiculacoes=[_v("ad", "111")])
    assert e.value.campanha_nome == "A"
    assert len(svc.listar(ORG)) == 1  # B was never created


def test_same_ref_different_nivel_is_fine(env):
    _c, svc = env
    svc.criar(ORG, nome="A", imovel_codigos=[], veiculacoes=[_v("ad", "111")])
    svc.criar(ORG, nome="B", imovel_codigos=[], veiculacoes=[_v("adset", "111")])


def test_repeated_veiculacao_in_payload_rejected(env):
    _c, svc = env
    with pytest.raises(VeiculacaoInvalida):
        svc.criar(ORG, nome="A", imovel_codigos=[], veiculacoes=[_v("ad", "1"), _v("ad", "1")])


def test_race_past_precheck_is_translated(env):
    c, svc = env
    svc.criar(ORG, nome="A", imovel_codigos=[], veiculacoes=[_v("ad", "111")])
    svc._check_veiculacoes = lambda *a, **k: None  # the pre-check loses a race
    with pytest.raises(VeiculacaoEmUso):
        svc.criar(ORG, nome="B", imovel_codigos=[], veiculacoes=[_v("ad", "111")])
    assert [x["nome"] for x in c.tables["campanhas"]] == ["A"]  # B rolled back


def test_patch_replaces_sets_and_keeps_own_refs(env):
    _c, svc = env
    a = svc.criar(ORG, nome="A", imovel_codigos=["ONE1"], veiculacoes=[_v("ad", "111")])
    out = svc.atualizar(ORG, a["id"], nome="A2", imovel_codigos=["ONE2"],
                        veiculacoes=[_v("ad", "111"), _v("campaign", "9")])
    assert out["nome"] == "A2"
    assert [i["codigo"] for i in out["imoveis"]] == ["ONE2"]
    assert len(out["veiculacoes"]) == 2
    only_nome = svc.atualizar(ORG, a["id"], nome="A3")
    assert len(only_nome["veiculacoes"]) == 2 and len(only_nome["imoveis"]) == 1


def test_patch_conflict_keeps_old_veiculacoes(env):
    _c, svc = env
    svc.criar(ORG, nome="A", imovel_codigos=[], veiculacoes=[_v("ad", "111")])
    b = svc.criar(ORG, nome="B", imovel_codigos=[], veiculacoes=[_v("ad", "222")])
    with pytest.raises(VeiculacaoEmUso):
        svc.atualizar(ORG, b["id"], veiculacoes=[_v("ad", "111")])
    assert svc.obter(ORG, b["id"])["veiculacoes"][0]["ref_codigo"] == "222"


def test_other_org_and_unknown_are_not_found(env):
    _c, svc = env
    a = svc.criar(ORG, nome="A", imovel_codigos=[], veiculacoes=[])
    for bad in (str(uuid4()), "not-a-uuid"):
        with pytest.raises(CampanhaNaoEncontrada):
            svc.obter(ORG, bad)
    with pytest.raises(CampanhaNaoEncontrada):
        svc.atualizar(OTHER, a["id"], nome="x")
    with pytest.raises(CampanhaNaoEncontrada):
        svc.excluir(OTHER, a["id"])


def test_soft_delete_hides_and_frees_refs(env):
    c, svc = env
    a = svc.criar(ORG, nome="A", imovel_codigos=["ONE1"], veiculacoes=[_v("ad", "111")])
    svc.excluir(ORG, a["id"])
    assert svc.listar(ORG) == []
    assert c.tables["campanhas"][0]["deleted_at"] is not None  # soft, row kept
    assert c.tables["campanha_veiculacoes"] == []
    with pytest.raises(CampanhaNaoEncontrada):
        svc.obter(ORG, a["id"])
    svc.criar(ORG, nome="B", imovel_codigos=[], veiculacoes=[_v("ad", "111")])  # id reusable
