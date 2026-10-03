"""Synthetic payment-shape variants, built ON TOP of the 6 spec variants
(`contrato_gerador_fixtures`) — never by editing them, so V1–V6 and their
render goldens stay byte-stable.

🔴 SYNTHETIC ONLY — every name, CPF, account and amount is invented.

Each builder is one payment shape the office's signed contracts use
(clause catalog §2 / §4):

- `sinal_em_partes`        the sinal paid in two tranches (783)
- `divisao_por_valor`      the sinal split between two payees by value
- `divisao_por_percentual` sinal AND intermediária split 50/50 (the second
                           cites the first's accounts and proportions)
- `fgts_com_valor`         FGTS inside the financing parcela, split known (192)
- `fgts_parcela_propria`   FGTS stored as its own parcela (folded in)
- `permuta_dois_imoveis`   ONE permuta parcela paid with two imóveis (873)
- `permuta_duas_parcelas`  two permuta parcelas, one imóvel each
- `onus_por_boleto`        the seller pays the lien off by bank slip (857/884)
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.modules.card_hub.contrato_gerador.dados import (
    DivisaoFavorecido,
    Favorecido,
    Financiamento,
)
from tests.modules.card_hub import contrato_gerador_fixtures as fx

#: A second payee — not one of the vendedores (FAVORECIDO_TERCEIRO aviso only).
FAV_2 = Favorecido(
    id="fav-2", nome="Beltrana Exemplo", cpf_cnpj=fx.cpf_sintetico("987654321"),
    banco="Banco Exemplo", agencia="0003", conta="77777-7",
)

SEGUNDO_ATIVO_ID = "permuta-2"


def _com_fav2(d):
    return replace(d, favorecidos=d.favorecidos + [FAV_2])


def sinal_em_partes():
    """V1 with the sinal paid as 30.000 at signing + 25.000 on a date (the
    intermediária drops to 45.000 so Σ parcelas still equals the price)."""
    d = fx.variante(1)
    p1 = replace(d.parcelas[0], valor=Decimal("30000.00"))
    p1b = fx.parcela(
        "p1b", "sinal", "25000.00", 2, vencimento=date(2026, 10, 14), forma_pagamento="PIX",
        favorecido_id="fav-v", dispara_corretagem=True,
    )
    p2 = replace(d.parcelas[1], valor=Decimal("45000.00"), ordem=3)
    p3 = replace(d.parcelas[2], ordem=4)
    return replace(d, parcelas=[p1, p1b, p2, p3])


def divisao_por_valor():
    d = _com_fav2(fx.variante(1))
    p1 = replace(
        d.parcelas[0], favorecido_id=None,
        divisao=(
            DivisaoFavorecido("fav-v", valor=Decimal("30000.00")),
            DivisaoFavorecido("fav-2", valor=Decimal("20000.00")),
        ),
    )
    return replace(d, parcelas=[p1] + d.parcelas[1:])


def divisao_por_percentual():
    d = _com_fav2(fx.variante(1))
    metade = (
        DivisaoFavorecido("fav-v", percentual=Decimal("50")),
        DivisaoFavorecido("fav-2", percentual=Decimal("50")),
    )
    p1 = replace(d.parcelas[0], favorecido_id=None, divisao=metade)
    p2 = replace(d.parcelas[1], favorecido_id=None, divisao=metade)
    return replace(d, parcelas=[p1, p2, d.parcelas[2]])


def fgts_com_valor():
    """V2 (FGTS on the financing) with the FGTS portion known: 100k of 400k."""
    d = fx.variante(2)
    return replace(d, parcelas=d.parcelas[:2] + [replace(d.parcelas[2], valor_fgts=Decimal("100000.00"))])


def fgts_parcela_propria():
    """V2 with the FGTS stored as its own parcela (no moment of its own)."""
    d = fx.variante(2)
    parcelas = [
        d.parcelas[0], d.parcelas[1], replace(d.parcelas[2], valor=Decimal("300000.00")),
        fx.parcela("p4", "fgts", "100000.00", 4),
    ]
    return replace(d, parcelas=parcelas, financiamento=Financiamento(True, "aprovado", True))


def _segundo_imovel(endereco_registro: str):
    return replace(
        fx.permuta_imovel(SEGUNDO_ATIVO_ID),
        descricao_matricula="MATRÍCULA Nº 65.432 - IMÓVEL: A vaga de garagem nº 7 situada na Avenida Amostra, nº 5.",
        inscricao_municipal="222.222.2222-2",
        matricula_numero="65432",
        endereco_registro_texto=endereco_registro,
    )


def permuta_dois_imoveis():
    d = fx.variante(5)
    parcelas = [
        replace(p, permuta_ativo_ids=(fx.PERMUTA_ATIVO_ID, SEGUNDO_ATIVO_ID)) if p.tipo == "permuta" else p
        for p in d.parcelas
    ]
    return replace(
        d, parcelas=parcelas,
        permuta_imoveis=d.permuta_imoveis + [_segundo_imovel("Avenida Amostra, nº 5")],
    )


def permuta_duas_parcelas():
    """V5 with its R$ 150.000 permuta split: 100.000 for the house + 50.000
    for a second imóvel, each its own permuta parcela."""
    d = fx.variante(5)
    parcelas = []
    for p in d.parcelas:
        if p.tipo == "permuta":
            parcelas.append(replace(p, valor=Decimal("100000.00")))
            parcelas.append(
                fx.parcela("p-permuta-2", "permuta", "50000.00", p.ordem + 1,
                           permuta_ativo_ids=(SEGUNDO_ATIVO_ID,))
            )
        else:
            parcelas.append(p)
    return replace(
        d, parcelas=parcelas,
        permuta_imoveis=d.permuta_imoveis + [_segundo_imovel("Rua Segunda Amostra, nº 9")],
    )


def onus_por_boleto():
    d = fx.variante(1)
    return fx._saldo_devedor(d, "vendedores_boleto", onus_prazo_dias=30)
