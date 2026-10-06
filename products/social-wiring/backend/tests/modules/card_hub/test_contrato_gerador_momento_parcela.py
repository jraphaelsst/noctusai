"""WHEN an intermediária parcela is paid (`frases._momento_parcela`).

In a financed deal the canonical wording ("por ocasião da assinatura do Contrato
de Financiamento Imobiliário, previsto para quitação da Parcela N") prints for an
intermediária whose evento is empty or just NAMES the financing contract. An
evento that states the deal's OWN timing (signed corpus deal 876: "em até 30
dias corridos da assinatura do contrato") must print as typed — overriding it
with the financing wording rewrote a negotiated prazo. All data synthetic."""
from __future__ import annotations

from datetime import date

from app.modules.card_hub.contrato_gerador import frases
from tests.modules.card_hub import contrato_gerador_fixtures as fx

_FIN = "por ocasião da assinatura do Contrato de Financiamento Imobiliário, previsto para quitação da Parcela 03"


def _momento(evento, *, vencimento=None, tem_financiamento=True, tipo="intermediaria"):
    p = fx.parcela("p2", tipo, "1000.00", 2, evento=evento, vencimento=vencimento)
    return frases._momento_parcela(p, tem_financiamento=tem_financiamento, ref_financiamento="03")


def test_empty_evento_prints_the_financing_wording():
    assert _momento(None) == _FIN


def test_evento_naming_the_financing_contract_prints_the_financing_wording():
    assert _momento("na assinatura do contrato de financiamento imobiliário") == _FIN


def test_a_negotiated_prazo_evento_prints_as_typed():
    assert _momento("em até 30 dias corridos da assinatura do contrato") == "em até 30 dias corridos da assinatura do contrato"


def test_vencimento_still_wins():
    assert _momento("em até 30 dias", vencimento=date(2026, 11, 3)) == "com vencimento em 03/11/2026"


def test_without_financing_the_evento_always_prints():
    assert _momento("na apresentação da matrícula", tem_financiamento=False) == "na apresentação da matrícula"
