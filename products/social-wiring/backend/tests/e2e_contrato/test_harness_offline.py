"""Offline tests for the harness's gap-marker render (`dados_com_marcadores`
+ `renderizar_em_memoria(com_marcadores=True)`) — synthetic fixtures only, no
database. The DB-touching paths (`relatorio_prontidao`, `pontuar_deal`) are
exercised by `noctus.dev.contract_score` against the live org, never here."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comparador  # noqa: E402
import harness  # noqa: E402

from tests.modules.card_hub import contrato_gerador_fixtures as fx  # noqa: E402

_GOLDEN_V1 = Path(__file__).resolve().parents[1] / "modules" / "card_hub" / "golden" / "contrato_v1.txt"


def _sem_cpf_e_nome_do_vendedor():
    d = fx.variante(1)
    vendedor = replace(d.vendedores[0], cpf=None, nome=None)
    # pin the instrument date: `renderizar_em_memoria` follows production
    # (`data_assinatura(dados, None)` → stored date, else TODAY)
    return replace(d, vendedores=[vendedor, *d.vendedores[1:]], assinatura_data=fx.ASSINATURA)


def test_marcadores_preenchem_so_texto_vazio_e_nao_mutam():
    d = _sem_cpf_e_nome_do_vendedor()
    marcado, n = harness.dados_com_marcadores(d)
    assert n >= 2
    assert marcado.vendedores[0].cpf == comparador.MARCADOR_LACUNA
    assert marcado.vendedores[0].nome == comparador.MARCADOR_LACUNA
    # the input is untouched, code fields are never marked
    assert d.vendedores[0].cpf is None
    assert marcado.vendedores[0].estado_civil == d.vendedores[0].estado_civil


def test_card_completo_nao_recebe_marcador_nos_campos_preenchidos():
    d = fx.variante(1)
    marcado, _ = harness.dados_com_marcadores(d)
    assert marcado.vendedores[0].cpf == d.vendedores[0].cpf
    assert marcado.compradores[0].nome == d.compradores[0].nome


def test_render_com_marcadores_vira_lacuna_no_scorecard():
    """The end-to-end shape of a not-`pronto` card: the render carries the
    marker where the value is missing, and the scorecard reports it as a GAP
    (`incompleto`), not as a number/wording failure."""
    renderizado = harness.renderizar_em_memoria(_sem_cpf_e_nome_do_vendedor(), com_marcadores=True)
    gerado = comparador.paragrafos_de_lista(renderizado.paragrafos)
    assert any(comparador.MARCADOR_LACUNA in p for p in gerado)
    card = comparador.pontuar(_GOLDEN_V1.read_text(encoding="utf-8").splitlines(), gerado)
    resumo = card.resumo()
    assert card.veredito == "incompleto", card.motivos()
    assert resumo["lacunas"] >= 2
    assert resumo["numeros_em_lacuna"] >= 1
    assert resumo["numeros_divergentes"] == 0, card.detalhe()["secoes"]


def test_preenchimentos_estruturais_permitem_render_de_card_incompleto():
    """The context builder ASSERTS a price, a sinal parcela, certidão dates
    and day counts. A card missing them still renders — with sentinels the
    scorecard reads as gaps (R$ 0,01 · 01/01/1900 · 999), never as values."""
    d = fx.variante(1)
    sem = replace(
        d,
        valor_negociado=None,
        parcelas=[p for p in d.parcelas if p.tipo != "sinal"],
        termos=replace(d.termos, posse_prazo_dias=None),
        assinatura_data=fx.ASSINATURA,
    )
    marcado, n = harness.dados_com_marcadores(sem)
    assert n >= 3
    assert any(p.tipo == "sinal" for p in marcado.parcelas)
    assert str(marcado.valor_negociado) == comparador.VALOR_LACUNA
    assert marcado.termos.posse_prazo_dias == comparador.INTEIRO_LACUNA
    assert sem.valor_negociado is None  # input untouched
    renderizado = harness.renderizar_em_memoria(sem, com_marcadores=True)
    card = comparador.pontuar(
        _GOLDEN_V1.read_text(encoding="utf-8").splitlines(),
        comparador.paragrafos_de_lista(renderizado.paragrafos),
    )
    assert card.lacunas >= 3
    assert all("0.01" not in t and "999" not in t for r in card.resultados for t in r.numeros_extras)


def test_clausulas_desligadas_vem_das_tabelas_do_gerador():
    """V5 has no intermediários → `tem_intermediacao` off → the intermediação
    title is reported as switched off (read from numeracao's own tables)."""
    from app.modules.card_hub.contrato_gerador import derivacao

    d5 = fx.variante(5)
    sw = derivacao.derivar_switches(d5, fx.politica_variante(5), fx.REFERENCIA)
    assert not sw["tem_intermediacao"]
    assert "DA INTERMEDIAÇÃO" in harness.clausulas_desligadas(sw)
    sw1 = derivacao.derivar_switches(fx.variante(1), fx.politica_variante(1), fx.REFERENCIA)
    assert "DA INTERMEDIAÇÃO" not in harness.clausulas_desligadas(sw1)
