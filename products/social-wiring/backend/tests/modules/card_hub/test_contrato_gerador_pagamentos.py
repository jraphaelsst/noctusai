"""Payment shapes the office's signed contracts use (clause catalog §2/§4/§9)
— each pinned by a RENDER (wording + lint clean) and by its GATE (what a
contradictory version of the same data refuses with).

- the sinal paid in tranches: ONE "Parcela 01", tranches enumerated, multa
  rescisória = Σ sinais [Q3];
- one parcela split among several favorecidos (by value / by percentage;
  a later parcela citing the same accounts and proportions);
- FGTS inside the financing parcela with explicit split amounts — from
  `valor_fgts` OR from a separate `fgts` parcela, the SAME paragraph;
- several permuta parcelas, and one permuta parcela with two imóveis;
- the seller paying the lien off by boleto;
- `CONFISSAO_EM_PARCELA_NAO_DIRETA` still refuses (no signed example).

All data synthetic (`contrato_gerador_fixtures_pagamentos`).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento, lint
from app.modules.card_hub.contrato_gerador.dados import DivisaoFavorecido
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub import contrato_gerador_fixtures_pagamentos as fp


def _avaliar(d, n: int):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _paragrafos(d, n: int) -> list[str]:
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    r = documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas) == []
    return r.paragrafos


def _parcela(paragrafos: list[str], num: str) -> str:
    return next(p for p in paragrafos if p.startswith(f"Parcela {num}:"))


def _codigos(av) -> list[str]:
    return [b["codigo"] for b in av.bloqueios]


# ─── sinal em partes ─────────────────────────────────────────────────────


class TestSinalEmPartes:
    def test_the_tranches_print_as_one_sinal_parcela(self):
        ps = _paragrafos(fp.sinal_em_partes(), 1)
        sinal = _parcela(ps, "01")
        assert sinal.startswith(
            "Parcela 01: Sinal e princípio de pagamento: R$ 55.000,00 (cinquenta e cinco mil reais), "
            "a serem pagos da seguinte forma: R$ 30.000,00 (trinta mil reais) no ato da assinatura do "
            "presente instrumento, por meio de PIX a ser realizada em favor do VENDEDOR: FULANO DE TAL"
        )
        assert (
            ", e R$ 25.000,00 (vinte e cinco mil reais) com vencimento em 14/10/2026, por meio de PIX "
            "na mesma conta corrente anteriormente informada, operando-se automaticamente a quitação"
        ) in sinal
        # Four stored parcelas, three printed — no gap in the numbering.
        assert [p[:10] for p in ps if p.startswith("Parcela ")] == ["Parcela 01", "Parcela 02", "Parcela 03"]

    def test_multa_rescisoria_is_the_sum_of_the_sinais(self):
        texto = "\n".join(_paragrafos(fp.sinal_em_partes(), 1))
        assert "multa rescisória no valor de R$ 55.000,00 (cinquenta e cinco mil reais)" in texto
        assert "perderá o valor pago do Sinal" in texto

    def test_marcos_count_the_printed_parcelas(self):
        texto = "\n".join(_paragrafos(fp.sinal_em_partes(), 1))
        # posse marco = the financing parcela (stored 4th, printed 03).
        assert "a contar do recebimento da parcela 03" in texto
        assert "por ocasião do recebimento da Parcela 01 da Cláusula" in texto

    def test_non_consecutive_sinais_block(self):
        d = fp.sinal_em_partes()
        parcelas = [replace(p, ordem=9) if p.id == "p1b" else p for p in d.parcelas]
        av = _avaliar(replace(d, parcelas=parcelas), 1)
        assert "SINAIS_NAO_CONSECUTIVOS" in _codigos(av)

    def test_a_tranche_split_among_favorecidos_blocks(self):
        d = fp.sinal_em_partes()
        d = replace(d, favorecidos=d.favorecidos + [fp.FAV_2])
        parcelas = [
            replace(p, favorecido_id=None, divisao=(
                DivisaoFavorecido("fav-v", valor=Decimal("15000.00")),
                DivisaoFavorecido("fav-2", valor=Decimal("15000.00")),
            )) if p.id == "p1" else p
            for p in d.parcelas
        ]
        assert "SINAL_EM_PARCELAS_COM_DIVISAO" in _codigos(_avaliar(replace(d, parcelas=parcelas), 1))

    def test_corretagem_flagged_on_only_some_tranches_blocks(self):
        d = fp.sinal_em_partes()
        parcelas = [replace(p, dispara_corretagem=False) if p.id == "p1b" else p for p in d.parcelas]
        assert "CORRETAGEM_SINAL_PARCIAL" in _codigos(_avaliar(replace(d, parcelas=parcelas), 1))

    def test_a_posse_marco_on_an_earlier_tranche_blocks(self):
        d = fp.sinal_em_partes()
        d = replace(d, termos=replace(d.termos, posse_marco_parcela_id="p1"))
        assert "POSSE_MARCO_PARTE_DO_SINAL" in _codigos(_avaliar(d, 1))

    def test_a_posse_marco_on_the_last_tranche_is_fine(self):
        d = fp.sinal_em_partes()
        d = replace(d, termos=replace(d.termos, posse_marco_parcela_id="p1b"))
        assert "POSSE_MARCO_PARTE_DO_SINAL" not in _codigos(_avaliar(d, 1))

    def test_a_one_line_per_parcela_caller_still_refuses_two_sinais(self):
        """The aditivo's restated schedule prints one line per stored parcela
        and calls `_negociacao` with the default `agrupar_parcelas=False`."""
        d = fp.sinal_em_partes()
        av = derivacao.Avaliacao()
        derivacao._negociacao(av, d, derivacao.derivar_switches(d, fx.politica_variante(1), fx.REFERENCIA), fx.ASSINATURA)
        assert "MAIS_DE_UM_SINAL" in _codigos(av)

    def test_each_tranche_needs_its_own_moment_and_favorecido(self):
        d = fp.sinal_em_partes()
        parcelas = [
            replace(p, vencimento=None, favorecido_id=None) if p.id == "p1b" else p for p in d.parcelas
        ]
        campos = [f["campo"] for f in _avaliar(replace(d, parcelas=parcelas), 1).faltando]
        assert "negociacao.parcela.p1b.momento" in campos
        assert "negociacao.parcela.p1b.favorecido" in campos


# ─── one parcela, several favorecidos ───────────────────────────────────


class TestDivisaoEntreFavorecidos:
    def test_by_value_prints_one_sub_item_per_share(self):
        ps = _paragrafos(fp.divisao_por_valor(), 1)
        sinal = _parcela(ps, "01")
        assert sinal.endswith(
            "nas contas correntes ora indicadas pelo Vendedor, por meio de PIX a ser realizada da seguinte forma:"
        )
        i = ps.index(sinal)
        assert ps[i + 1].startswith("01.1) R$ 30.000,00 (trinta mil reais) em favor do VENDEDOR: FULANO DE TAL")
        assert ps[i + 1].endswith(";")
        assert ps[i + 2] == (
            "01.2) R$ 20.000,00 (vinte mil reais) em favor de BELTRANA EXEMPLO, CPF: 987.654.321-00, "
            "Banco Exemplo, Agência 0003, Conta 77777-7."
        )
        # The seller's account was printed in the split — the next parcela cites it.
        assert "na mesma conta corrente anteriormente informada" in _parcela(ps, "02")

    def test_by_percentage_prints_value_and_share(self):
        ps = _paragrafos(fp.divisao_por_percentual(), 1)
        i = ps.index(_parcela(ps, "01"))
        assert ps[i + 1].startswith(
            "01.1) R$ 25.000,00 (vinte e cinco mil reais), correspondentes a 50% (cinquenta por cento) "
            "da parcela, em favor do VENDEDOR"
        )

    def test_a_later_parcela_with_the_same_split_cites_it(self):
        ps = _paragrafos(fp.divisao_por_percentual(), 1)
        p2 = _parcela(ps, "02")
        assert p2.endswith(
            "por meio de transferência nas mesmas contas correntes e proporções informadas na Parcela 01."
        )
        assert not any(p.startswith("02.1)") for p in ps)

    def _com_divisao(self, *partes, **parcela):
        d = fp.divisao_por_valor()
        p1 = replace(d.parcelas[0], divisao=tuple(partes), **parcela)
        return replace(d, parcelas=[p1] + d.parcelas[1:])

    def test_shares_that_do_not_add_up_block(self):
        d = self._com_divisao(
            DivisaoFavorecido("fav-v", valor=Decimal("30000.00")),
            DivisaoFavorecido("fav-2", valor=Decimal("10000.00")),
        )
        assert "DIVISAO_SOMA_DIVERGE" in _codigos(_avaliar(d, 1))

    def test_percentages_that_do_not_add_up_block(self):
        d = self._com_divisao(
            DivisaoFavorecido("fav-v", percentual=Decimal("50")),
            DivisaoFavorecido("fav-2", percentual=Decimal("40")),
        )
        assert "DIVISAO_PERCENTUAL_DIVERGE" in _codigos(_avaliar(d, 1))

    def test_percentages_that_leave_a_stray_cent_block(self):
        d = fp.divisao_por_valor()
        d = replace(d, favorecidos=d.favorecidos + [replace(fp.FAV_2, id="fav-3", nome="Terceira Exemplo")])
        # 33,3333% of R$ 50.000,01 rounds to 16.666,65 twice + 16.666,70 = 50.000,00.
        p1 = replace(d.parcelas[0], valor=Decimal("50000.01"), divisao=(
            DivisaoFavorecido("fav-v", percentual=Decimal("33.3333")),
            DivisaoFavorecido("fav-2", percentual=Decimal("33.3333")),
            DivisaoFavorecido("fav-3", percentual=Decimal("33.3334")),
        ))
        p2 = replace(d.parcelas[1], valor=Decimal("49999.99"))
        assert _codigos(_avaliar(replace(d, parcelas=[p1, p2, d.parcelas[2]]), 1)) == ["DIVISAO_PERCENTUAL_INEXATO"]

    def test_mixing_values_and_percentages_blocks(self):
        d = self._com_divisao(
            DivisaoFavorecido("fav-v", valor=Decimal("25000.00")),
            DivisaoFavorecido("fav-2", percentual=Decimal("50")),
        )
        assert "DIVISAO_MISTA" in _codigos(_avaliar(d, 1))

    def test_a_single_favorecido_and_a_split_together_block(self):
        d = fp.divisao_por_valor()
        p1 = replace(d.parcelas[0], favorecido_id="fav-v")
        assert "FAVORECIDO_E_DIVISAO" in _codigos(_avaliar(replace(d, parcelas=[p1] + d.parcelas[1:]), 1))

    def test_an_unknown_favorecido_blocks_and_a_deleted_one_is_missing(self):
        d = self._com_divisao(
            DivisaoFavorecido("nao-existe", valor=Decimal("30000.00")),
            DivisaoFavorecido(None, valor=Decimal("20000.00")),
        )
        av = _avaliar(d, 1)
        assert "FAVORECIDO_INEXISTENTE" in _codigos(av)
        assert "negociacao.parcela.p1.divisao.2.favorecido" in [f["campo"] for f in av.faltando]

    def test_a_share_with_no_amount_is_missing(self):
        d = self._com_divisao(
            DivisaoFavorecido("fav-v", valor=Decimal("30000.00")),
            DivisaoFavorecido("fav-2"),
        )
        assert "negociacao.parcela.p1.divisao.2.valor" in [f["campo"] for f in _avaliar(d, 1).faltando]

    def test_a_share_without_a_printable_account_is_missing(self):
        d = fp.divisao_por_valor()
        d = replace(d, favorecidos=[f if f.id != "fav-2" else replace(f, conta=None, pix=None) for f in d.favorecidos])
        assert "negociacao.favorecido.fav-2.conta" in [f["campo"] for f in _avaliar(d, 1).faltando]

    def test_a_split_on_the_financing_parcela_blocks(self):
        d = fp.divisao_por_valor()
        p3 = replace(d.parcelas[2], divisao=(
            DivisaoFavorecido("fav-v", valor=Decimal("200000.00")),
            DivisaoFavorecido("fav-2", valor=Decimal("200000.00")),
        ))
        assert "DIVISAO_EM_PARCELA_SEM_FAVORECIDO" in _codigos(_avaliar(replace(d, parcelas=d.parcelas[:2] + [p3]), 1))

    def test_a_one_share_split_blocks(self):
        d = self._com_divisao(DivisaoFavorecido("fav-v", valor=Decimal("50000.00")))
        assert "DIVISAO_COM_UM_FAVORECIDO" in _codigos(_avaliar(d, 1))


# ─── FGTS ────────────────────────────────────────────────────────────────

_FGTS_SPLIT = (
    "Parcela 03: R$ 400.000,00 (quatrocentos mil reais), onde será utilizado R$ 100.000,00 (cem mil reais), "
    "por meio do uso das contas vinculadas ao FGTS e R$ 300.000,00 (trezentos mil reais) por meio de recursos "
    "de financiamento imobiliário e/ou moeda corrente nacional, com prazo máximo de pagamento de 90 (noventa) "
    "dias corridos, a contar da assinatura do presente instrumento."
)


class TestFgts:
    def test_the_known_split_prints_the_signed_wording(self):
        assert _parcela(_paragrafos(fp.fgts_com_valor(), 2), "03") == _FGTS_SPLIT

    def test_a_separate_fgts_parcela_prints_the_same_paragraph(self):
        ps = _paragrafos(fp.fgts_parcela_propria(), 2)
        assert _parcela(ps, "03") == _FGTS_SPLIT
        assert not any(p.startswith("Parcela 04:") for p in ps)

    def test_fgts_not_smaller_than_the_parcela_blocks(self):
        d = fp.fgts_com_valor()
        d = replace(d, parcelas=d.parcelas[:2] + [replace(d.parcelas[2], valor_fgts=Decimal("400000.00"))])
        assert "FGTS_MAIOR_QUE_PARCELA" in _codigos(_avaliar(d, 2))

    def test_fgts_amounts_without_fgts_on_the_financing_block(self):
        d = replace(fp.fgts_com_valor(), financiamento=replace(fx.variante(2).financiamento, fgts=False))
        assert "FGTS_NAO_MARCADO_NO_FINANCIAMENTO" in _codigos(_avaliar(d, 2))

    def test_both_fgts_sources_at_once_block(self):
        d = fp.fgts_parcela_propria()
        parcelas = [replace(p, valor_fgts=Decimal("50000.00")) if p.tipo == "financiamento" else p for p in d.parcelas]
        assert "FGTS_EM_DUPLICIDADE" in _codigos(_avaliar(replace(d, parcelas=parcelas), 2))

    def test_two_fgts_parcelas_block(self):
        d = fp.fgts_parcela_propria()
        parcelas = d.parcelas[:3] + [
            fx.parcela("p4", "fgts", "50000.00", 4), fx.parcela("p5", "fgts", "50000.00", 5),
        ]
        assert "MAIS_DE_UMA_PARCELA_FGTS" in _codigos(_avaliar(replace(d, parcelas=parcelas), 2))

    def test_an_fgts_parcela_without_a_financing_parcela_blocks(self):
        d = fp.fgts_parcela_propria()
        parcelas = [replace(p, tipo="direta", forma_pagamento="PIX", favorecido_id="fav-v")
                    if p.tipo == "financiamento" else p for p in d.parcelas]
        assert "PARCELA_FGTS_SEM_FINANCIAMENTO" in _codigos(_avaliar(replace(d, parcelas=parcelas), 2))


# ─── permuta ─────────────────────────────────────────────────────────────


class TestPermuta:
    def test_one_permuta_parcela_with_two_imoveis(self):
        ps = _paragrafos(fp.permuta_dois_imoveis(), 5)
        p5 = _parcela(ps, "05")
        assert "por permuta dos imóveis de propriedade da Compradora" in p5
        assert "Matrícula Nº 54.321" in p5 and "Matrícula Nº 65.432" in p5
        texto = "\n".join(ps)
        assert "Escritura Pública de Permuta dos imóveis melhor descritos na Parcela 05 acima" in texto
        assert "entrega da posse dos imóveis situados à Avenida Amostra, nº 5 ao VENDEDOR" in texto

    def test_two_permuta_parcelas_each_print_their_own_imovel(self):
        ps = _paragrafos(fp.permuta_duas_parcelas(), 5)
        p5, p6 = _parcela(ps, "05"), _parcela(ps, "06")
        assert "Matrícula Nº 54.321" in p5 and "65.432" not in p5
        assert "Matrícula Nº 65.432" in p6 and "54.321" not in p6
        texto = "\n".join(ps)
        assert "Escritura Pública de Permuta dos imóveis melhor descritos nas Parcelas 05 e 06 acima" in texto
        assert "posse dos imóveis situados à Avenida Amostra, nº 5 e à Rua Segunda Amostra, nº 9" in texto
        assert "obstáculos para acesso aos imóveis situados à Avenida Amostra" in texto

    def test_one_imovel_keeps_the_singular_wording(self):
        texto = "\n".join(_paragrafos(fx.variante(5), 5))
        assert "Escritura Pública de Permuta do imóvel melhor descrito na Parcela 05 acima" in texto
        assert "entrega da posse do imóvel situado à" in texto

    def test_a_second_permuta_parcela_without_imovel_is_missing(self):
        d = fp.permuta_duas_parcelas()
        parcelas = [replace(p, permuta_ativo_ids=()) if p.id == "p-permuta-2" else p for p in d.parcelas]
        av = _avaliar(replace(d, parcelas=parcelas), 5)
        assert "negociacao.parcela.p-permuta-2.permuta_imoveis" in [f["campo"] for f in av.faltando]
        assert "PERMUTA_IMOVEL_SEM_PARCELA" in _codigos(av)

    def test_a_link_to_an_imovel_not_loaded_blocks(self):
        d = fp.permuta_duas_parcelas()
        av = _avaliar(replace(d, permuta_imoveis=d.permuta_imoveis[:1]), 5)
        assert "PERMUTA_IMOVEL_NAO_CARREGADO" in _codigos(av)


# ─── ônus quitado por boleto ─────────────────────────────────────────────


class TestOnusPorBoleto:
    def test_the_seller_pays_off_by_boleto(self):
        texto = "\n".join(_paragrafos(fp.onus_por_boleto(), 1))
        assert (
            "conforme descrito na Av.02 da Matrícula do imóvel, o qual deverá ser quitado através de boleto "
            "bancário emitido pela instituição financeira responsável, onde O VENDEDOR terá o prazo de até "
            "30 (trinta) dias corridos para realizar a quitação e apresentar o comprovante de pagamento."
        ) in texto

    def test_the_prazo_is_required(self):
        d = fp.onus_por_boleto()
        d = replace(d, termos=replace(d.termos, onus_prazo_dias=None))
        assert "negociacao.onus_prazo_dias" in [f["campo"] for f in _avaliar(d, 1).faltando]


# ─── still refused ───────────────────────────────────────────────────────


class TestConfissaoEmParcelaNaoDireta:
    def test_still_blocks_no_signed_contract_has_it(self):
        d = fx.variante(1)
        parcelas = [replace(p, confissao_divida=True, vencimento=date(2027, 1, 10)) if p.tipo == "intermediaria"
                    else p for p in d.parcelas]
        assert "CONFISSAO_EM_PARCELA_NAO_DIRETA" in _codigos(_avaliar(replace(d, parcelas=parcelas), 1))
