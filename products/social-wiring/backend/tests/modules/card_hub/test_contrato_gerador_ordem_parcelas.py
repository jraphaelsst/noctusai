"""Parcela numbering: persisted `ordem` decides, the sinal is always the first
payment, and every amount stays attached to its own number. One ordering point
(`derivacao.parcelas_ordenadas`) feeds numbering, references and amounts."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub import contrato_gerador_fixtures_pagamentos as fp


def _render(d, n: int = 1) -> list[str]:
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    r = documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    return r.paragrafos


def _linhas(ps: list[str]) -> dict[str, str]:
    return {p[8:10]: p for p in ps if p.startswith("Parcela ") and p[10:11] == ":"}


def test_ordem_is_respected_whatever_the_read_order():
    d = fx.variante(1)  # sinal 50k (1), intermediária 50k (2), financiamento 400k (3)
    ps = _render(replace(d, parcelas=[d.parcelas[2], d.parcelas[0], d.parcelas[1]]))
    linhas = _linhas(ps)
    assert "Sinal" in linhas["01"] and "R$ 50.000,00" in linhas["01"]
    assert "R$ 400.000,00" in linhas["03"]
    assert "perderá o valor pago na Parcela 01 (Sinal)" in "\n".join(ps)


def test_sinal_stored_last_still_prints_as_parcela_01_with_its_own_amount():
    """The deals 858/863/869 shape: the sinal was created after the
    auto-suggested financiamento/intermediária, so its `ordem` is the highest."""
    d = fx.variante(1)
    sinal, inter, fin = d.parcelas
    guardadas = [replace(inter, ordem=0), replace(fin, ordem=1), replace(sinal, ordem=2)]
    ps = _render(replace(d, parcelas=guardadas))
    linhas = _linhas(ps)
    assert "Sinal" in linhas["01"] and "R$ 50.000,00" in linhas["01"]
    assert "R$ 400.000,00" in linhas["03"]  # financiamento keeps its relative order
    assert "perderá o valor pago na Parcela 01 (Sinal)" in "\n".join(ps)
    assert [p.tipo for p in derivacao.parcelas_ordenadas(replace(d, parcelas=guardadas))] == [
        "sinal", "intermediaria", "financiamento",
    ]


def test_sinal_in_tranches_stored_last_is_hoisted_together():
    d = fp.sinal_em_partes()  # sinal(1), sinal(2), intermediária(3), financiamento(4)
    s1, s2, inter, fin = d.parcelas
    guardadas = [replace(inter, ordem=0), replace(fin, ordem=1), replace(s1, ordem=2), replace(s2, ordem=3)]
    ordenadas = derivacao.parcelas_ordenadas(replace(d, parcelas=guardadas))
    assert [p.id for p in ordenadas] == [s1.id, s2.id, inter.id, fin.id]


def test_operator_order_among_the_other_parcelas_is_kept():
    d = fx.variante(1)
    sinal, inter, fin = d.parcelas
    ordenadas = derivacao.parcelas_ordenadas(
        replace(d, parcelas=[replace(fin, ordem=0), replace(sinal, ordem=1), replace(inter, ordem=2)])
    )
    assert [p.tipo for p in ordenadas] == ["sinal", "financiamento", "intermediaria"]
