"""Contract specifications (owner direction 2026-10-24, migration 308).

WHAT THESE PIN
--------------
- the catalogue is coherent: every `requer`/`exclusiva_com`/`dispensa` names
  a real key, exclusivity is declared on both sides, every clause is a real
  `numeracao.ORDEM_CLAUSULAS` key, every implied switch is a real
  `derivar_switches` key;
- every requisito is a falta key `derivacao` actually emits (an inventory
  read off its AST, plus a runtime read for the permuta imóvel fields) —
  except the named PENDING owner decisions (G1);
- `sugerir` is stable per fixture variant, always `validar`-clean, and
  `modelo_de(sugerir(sw)) == modelo_derivado(sw)` for every variant;
- `validar` refuses unknown / repeated / missing-base / missing-`requer` /
  exclusive selections with a ValueError naming the culprit;
- `conflitos` names data that contradicts a selection, never absent data;
- `PUT .../contratos/{id}/especificacoes`: strict 401, 400 on an incoherent
  selection (nothing written), 404 for a foreign contract, the stored set +
  `modelo` on success, and the carregador reads it into `DadosContrato`.
"""
from __future__ import annotations

import ast
import itertools
import re
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.card_hub.contrato_gerador import derivacao, numeracao
from app.modules.card_hub.contrato_gerador import especificacoes as esp
from app.modules.card_hub.contrato_gerador.carregador import _especificacoes
from app.modules.card_hub.contrato_gerador.dados import Endereco
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub import contrato_gerador_fixtures_pagamentos as fxp
from tests.modules.card_hub.test_contratos import _auth, _criar, _seed

VARIANTES = range(1, 7)
PAGAMENTOS = (
    fxp.sinal_em_partes, fxp.divisao_por_valor, fxp.divisao_por_percentual, fxp.fgts_com_valor,
    fxp.fgts_parcela_propria, fxp.permuta_dois_imoveis, fxp.permuta_duas_parcelas, fxp.onus_por_boleto,
)


def _switches(d, n: int = 1):
    return derivacao.derivar_switches(d, fx.politica_variante(n), fx.REFERENCIA)


# ─── catalogue coherence ──────────────────────────────────────────────────


class TestCatalogueShape:
    def test_keys_unique_axes_known(self):
        assert len(esp.CHAVES) == len(esp.CATALOGO)
        assert {e.eixo for e in esp.CATALOGO} <= set(esp.EIXOS)
        assert esp.CHAVES == (
            "compra_venda", "a_vista", "sinal_saldo", "financiamento_bancario", "fgts",
            "parcelas_diretas", "intermediarias", "confissao_divida", "permuta", "intermediacao",
        )
        assert esp.CATALOGO_VERSAO == 1

    def test_references_name_real_keys_and_exclusivity_is_symmetric(self):
        for e in esp.CATALOGO:
            for r in (*e.requer, *e.exclusiva_com):
                assert r in esp.POR_CHAVE, (e.chave, r)
            for x in e.exclusiva_com:
                assert e.chave in esp.POR_CHAVE[x].exclusiva_com, (e.chave, x)
            assert set(e.dispensa) <= {r for o in esp.CATALOGO for r in o.requisitos}

    def test_clauses_are_registry_keys_and_conditionals_are_owned(self):
        todas = [c for e in esp.CATALOGO for c in e.clausulas]
        assert len(todas) == len(set(todas))
        assert set(todas) <= set(numeracao.ORDEM_CLAUSULAS)
        # Office/modalidade-driven conditionals are not deal specifications.
        assert set(numeracao.ORDEM_CLAUSULAS) - set(todas) == {"declaracao_partes", "assinatura_digital"}
        for e in esp.CATALOGO:
            for c in e.clausulas:
                if c in numeracao.CLAUSULA_CONDICIONAL:
                    assert numeracao.CLAUSULA_CONDICIONAL[c] in e.switches_implicados

    def test_implied_switches_are_real(self):
        sw = _switches(fx.variante(1))
        for e in esp.CATALOGO:
            assert set(e.switches_implicados) <= set(sw), e.chave

    def test_g1_is_a_named_pending_requisito_on_a_vista(self):
        assert "negociacao.multa_rescisoria_base" in esp.POR_CHAVE["a_vista"].requisitos
        assert "negociacao.multa_rescisoria_base" in esp.PENDENTES_DECISAO


# ─── requisitos are real falta keys ───────────────────────────────────────


def _inventario_falta() -> list[re.Pattern[str]]:
    """Every `av.falta(<campo>, ...)` key in derivacao.py as a regex: a
    literal, or an f-string whose interpolations match any text (an `alvo` prefix spans segments).
    Keys that are interpolation-only (`f"{alvo}.{campo}"`) carry no literal
    to check against and are left to the runtime read below."""
    arvore = ast.parse(Path(derivacao.__file__).read_text(encoding="utf-8"))
    saida: list[re.Pattern[str]] = []

    def _de(no) -> list[str]:
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            return [re.escape(no.value)]
        if isinstance(no, ast.IfExp):
            return _de(no.body) + _de(no.orelse)
        if isinstance(no, ast.JoinedStr):
            partes = [
                re.escape(v.value) if isinstance(v, ast.Constant) else ".+" for v in no.values
            ]
            literal = "".join(v.value for v in no.values if isinstance(v, ast.Constant))
            return ["".join(partes)] if literal.strip(".") else []
        return []

    for no in ast.walk(arvore):
        if (
            isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
            and no.func.attr == "falta" and no.args
        ):
            saida += [re.compile(f"^{p}$") for p in _de(no.args[0])]
    return saida


def _faltas_da_permuta() -> set[str]:
    d = fx.variante(5)
    vazio = replace(
        d.permuta_imoveis[0], inscricao_municipal=None, matricula_numero=None, cartorio=None,
        endereco=Endereco(), endereco_registro_texto="Rua Outra, 1",
    )
    d = replace(d, permuta_imoveis=[vazio])
    av = derivacao.avaliar(d, _switches(d, 5), fx.politica_variante(5), fx.ASSINATURA, fx.REFERENCIA)
    return {f["campo"] for f in av.faltando}


def test_every_requisito_is_a_falta_key_derivacao_emits():
    inventario = _inventario_falta()
    runtime = _faltas_da_permuta()
    for e in esp.CATALOGO:
        for padrao in e.requisitos:
            if padrao in esp.PENDENTES_DECISAO:
                continue
            exemplo = padrao.replace("*", "permuta-1")
            assert any(rx.match(exemplo) for rx in inventario) or exemplo in runtime, (e.chave, padrao)


def test_pattern_matching():
    assert esp.exige({"negociacao.parcela.*.valor"}, "negociacao.parcela.p1.valor")
    assert not esp.exige({"negociacao.parcela.*.valor"}, "negociacao.parcela.p1.x.valor")
    assert esp.governa("negociacao.pct_comissao")
    assert not esp.governa("qualificacao.profissao")


# ─── sugerir: stable, valid, modelo parity ────────────────────────────────

SUGERIDO = {
    1: ["compra_venda", "sinal_saldo", "financiamento_bancario", "intermediarias", "intermediacao"],
    2: ["compra_venda", "sinal_saldo", "financiamento_bancario", "fgts", "intermediarias", "intermediacao"],
    3: ["compra_venda", "sinal_saldo", "financiamento_bancario", "intermediarias", "intermediacao"],
    4: ["compra_venda", "a_vista", "sinal_saldo", "intermediacao"],
    5: ["compra_venda", "sinal_saldo", "financiamento_bancario", "parcelas_diretas", "confissao_divida",
        "permuta"],
    6: ["compra_venda", "sinal_saldo", "financiamento_bancario", "intermediarias", "permuta"],
}


@pytest.mark.parametrize("n", VARIANTES)
def test_sugerir_is_stable_per_variant(n):
    sw = _switches(fx.variante(n), n)
    assert esp.sugerir(sw) == SUGERIDO[n]
    assert esp.sugerir(sw) == esp.sugerir(dict(sw))


@pytest.mark.parametrize("n", VARIANTES)
def test_modelo_de_matches_modelo_derivado_per_variant(n):
    sw = _switches(fx.variante(n), n)
    assert esp.modelo_de(esp.sugerir(sw)) == derivacao.modelo_derivado(sw)
    assert esp.conflitos(esp.sugerir(sw), sw) == []


@pytest.mark.parametrize("builder", PAGAMENTOS, ids=lambda b: b.__name__)
def test_payment_shapes_suggest_valid_conflict_free_sets(builder):
    sw = _switches(builder())
    sug = esp.sugerir(sw)
    assert esp.validar(sug) == tuple(sug)
    assert esp.modelo_de(sug) == derivacao.modelo_derivado(sw)
    assert esp.conflitos(sug, sw) == []


def _combinacoes_coerentes():
    """Every switch combination `derivar_switches` CAN produce on the
    payment/permuta/intermediação switches (fgts ⇒ financiamento, confissão
    ⇒ parcelas diretas, à vista ⇒ neither)."""
    chaves = ("tem_financiamento", "tem_fgts", "tem_parcelas_diretas", "tem_confissao",
              "tem_intermediaria", "tem_permuta", "tem_intermediacao", "a_vista")
    for valores in itertools.product((False, True), repeat=len(chaves)):
        sw = dict(zip(chaves, valores))
        if sw["tem_fgts"] and not sw["tem_financiamento"]:
            continue
        if sw["tem_confissao"] and not sw["tem_parcelas_diretas"]:
            continue
        if sw["a_vista"] and (sw["tem_financiamento"] or sw["tem_parcelas_diretas"]):
            continue
        yield sw


def test_every_coherent_switch_combination_suggests_a_valid_conflict_free_set():
    vistos = 0
    for sw in _combinacoes_coerentes():
        sug = esp.sugerir(sw)
        assert esp.validar(sug) == tuple(sug), sw
        assert esp.modelo_de(sug) == derivacao.modelo_derivado(sw), sw
        assert esp.conflitos(sug, sw) == [], sw
        vistos += 1
    assert vistos > 50


# ─── validar ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "selecao, culpado",
    [
        (["compra_venda", "leasing"], "leasing"),
        (["compra_venda", "permuta", "permuta"], "permuta"),
        (["a_vista"], "compra_venda"),
        ([], "compra_venda"),
        (["compra_venda", "fgts"], "financiamento_bancario"),
        (["compra_venda", "confissao_divida"], "parcelas_diretas"),
        (["compra_venda", "a_vista", "financiamento_bancario"], "financiamento_bancario"),
        (["compra_venda", "a_vista", "parcelas_diretas"], "parcelas_diretas"),
    ],
)
def test_validar_refuses_naming_the_culprit(selecao, culpado):
    with pytest.raises(ValueError, match=culpado):
        esp.validar(selecao)


def test_validar_returns_catalogue_order():
    assert esp.validar(["intermediacao", "permuta", "compra_venda"]) == (
        "compra_venda", "permuta", "intermediacao",
    )


# ─── requisitos / modelo_de / conflitos ───────────────────────────────────


def test_requisitos_union_and_g1_dispensed_by_sinal():
    so_vista = esp.requisitos(["compra_venda", "a_vista"])
    assert "negociacao.multa_rescisoria_base" in so_vista
    assert "negociacao.parcela_sinal" not in so_vista
    com_sinal = esp.requisitos(["compra_venda", "a_vista", "sinal_saldo"])
    assert "negociacao.multa_rescisoria_base" not in com_sinal
    assert "negociacao.parcela_sinal" in com_sinal
    fin = esp.requisitos(["compra_venda", "sinal_saldo", "financiamento_bancario"])
    assert {"financiamento", "financiamento.situacao"} <= fin
    assert "negociacao.pct_comissao" not in fin
    assert "negociacao.pct_comissao" in esp.requisitos(["compra_venda", "intermediacao"])


def test_modelo_de():
    assert esp.modelo_de(["compra_venda"]) == esp.MODELO_COMPRA_VENDA
    assert esp.modelo_de(["compra_venda", "a_vista"]) == esp.MODELO_A_VISTA
    assert esp.modelo_de(["compra_venda", "a_vista", "permuta"]) == esp.MODELO_PERMUTA
    assert esp.modelo_de(["compra_venda", "sinal_saldo", "financiamento_bancario"]) == esp.MODELO_COMPRA_VENDA


class TestConflitos:
    def test_a_vista_with_a_financiamento_parcela(self):
        sw = _switches(fx.variante(1))
        msgs = esp.conflitos(["compra_venda", "a_vista", "sinal_saldo", "intermediarias", "intermediacao"], sw)
        assert any("À vista" in m and "financiamento bancário" in m for m in msgs)

    def test_fgts_without_a_financiamento_parcela(self):
        sw = _switches(fx.variante(4))  # sinal + saldo, no financing
        msgs = esp.conflitos(["compra_venda", "sinal_saldo", "financiamento_bancario", "fgts", "intermediacao"], sw)
        assert any("Uso de FGTS" in m for m in msgs)
        assert any("Financiamento bancário" in m for m in msgs)

    def test_data_facet_not_selected(self):
        sw = _switches(fx.variante(5))
        msgs = esp.conflitos(["compra_venda", "sinal_saldo", "financiamento_bancario", "parcelas_diretas",
                              "confissao_divida"], sw)
        assert msgs == ["Os dados do negócio têm permuta, mas a especificação 'Permuta' não está selecionada."]

    def test_absent_data_is_never_a_conflict(self):
        sw = {k: False for k in _switches(fx.variante(1))}
        assert esp.conflitos(["compra_venda", "sinal_saldo", "financiamento_bancario", "permuta",
                              "intermediacao"], sw) == []

    def test_a_g1_a_vista_without_sinal_is_not_a_conflict(self):
        sw = _switches(fx.variante(4))
        assert esp.conflitos(["compra_venda", "a_vista", "intermediacao"], sw) == []


# ─── carregador ───────────────────────────────────────────────────────────


def test_carregador_reads_null_as_legacy_and_keeps_the_stored_order():
    assert _especificacoes(None) is None
    assert _especificacoes(["compra_venda", "permuta"]) == ("compra_venda", "permuta")
    assert fx.base_v1().especificacoes is None and fx.base_v1().especificacoes_versao is None


# ─── the route ────────────────────────────────────────────────────────────


class TestEspecificacoesRoute:
    def _url(self, cid, contrato_id) -> str:
        return f"/api/clientes/{cid}/contratos/{contrato_id}/especificacoes"

    def test_unauthenticated_is_a_strict_401(self, anon_client, scoped, fake_storage):
        cid, _aid = _seed(scoped)
        r = anon_client.put(self._url(cid, uuid4()), json={"especificacoes": ["compra_venda"]})
        assert r.status_code == 401, r.text

    def test_stores_the_selection_in_catalogue_order(self, client, scoped, fake_storage):
        cid, _aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]

        r = client.put(
            self._url(cid, contrato_id),
            json={"especificacoes": ["permuta", "compra_venda", "a_vista"]},
            headers=_auth(),
        )

        assert r.status_code == 200, r.text
        assert r.json() == {
            "especificacoes": ["compra_venda", "a_vista", "permuta"],
            "especificacoes_versao": esp.CATALOGO_VERSAO,
            "modelo": esp.MODELO_PERMUTA,
        }
        row = scoped.table("atendimento_contratos").select("*").execute().data[0]
        assert row["especificacoes"] == ["compra_venda", "a_vista", "permuta"]
        assert row["especificacoes_versao"] == esp.CATALOGO_VERSAO

    @pytest.mark.parametrize("selecao", [["compra_venda", "fgts"], ["compra_venda", "leasing"], []])
    def test_an_incoherent_selection_is_a_400_that_writes_nothing(self, client, scoped, fake_storage, selecao):
        cid, _aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]

        r = client.put(self._url(cid, contrato_id), json={"especificacoes": selecao}, headers=_auth())

        assert r.status_code == 400, r.text
        row = scoped.table("atendimento_contratos").select("*").execute().data[0]
        assert row.get("especificacoes") is None

    def test_an_unknown_body_field_is_a_422(self, client, scoped, fake_storage):
        cid, _aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        r = client.put(
            self._url(cid, contrato_id),
            json={"especificacoes": ["compra_venda"], "modelo": "x"},
            headers=_auth(),
        )
        assert r.status_code == 422, r.text

    def test_a_foreign_contrato_is_a_404(self, client, scoped, fake_storage):
        cid, _aid = _seed(scoped)
        r = client.put(self._url(cid, uuid4()), json={"especificacoes": ["compra_venda"]}, headers=_auth())
        assert r.status_code == 404, r.text

    def test_the_contract_read_carries_the_selection(self, client, scoped, fake_storage):
        cid, _aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        client.put(self._url(cid, contrato_id), json={"especificacoes": ["compra_venda"]}, headers=_auth())

        contratos = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()
        alvo = next(c for c in contratos["contratos"] if c["id"] == contrato_id)
        assert alvo["especificacoes"] == ["compra_venda"]
        assert alvo["especificacoes_versao"] == esp.CATALOGO_VERSAO
