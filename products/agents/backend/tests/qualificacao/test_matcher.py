"""The ``trecho`` matcher (CONTRACT risk 3): accents, case, punctuation, windows, refusals."""
from __future__ import annotations

import pytest

from app.qualificacao.matcher import MAX_TRECHO, conferir_trecho, normalizar


def test_normalizar_folds_accents_case_and_punctuation():
    assert normalizar("  Três  QUARTOS,  c/ suíte!! ") == "tres quartos c suite"
    assert normalizar("R$ 450.000,00") == "r 450 000 00"


@pytest.mark.parametrize("trecho,msgs", [
    ("tres quartos", ["Quero uma casa de TRÊS quartos"]),
    ("três quartos", ["quero casa de tres quartos"]),
    ("450 mil", ["no maximo 450 mil, ta?"]),
    ("até 450.000", ["Até 450.000!"]),
    ("centro, jardim", ["prefiro centro. Jardim tambem"]),  # punctuation folded
    ("financiamento", ["oi", "queria saber de preço", "vou de financiamento"]),
    ("casa no centro", ["quero uma casa", "no centro"]),  # answer split over two bubbles
])
def test_matches(trecho, msgs):
    assert conferir_trecho(trecho, msgs) == (True, None)


@pytest.mark.parametrize("trecho,msgs,codigo", [
    ("quatro quartos", ["quero tres quartos"], "trecho_nao_confere"),
    ("tres quartos", [], "trecho_nao_confere"),
    (None, ["x"], "trecho_ausente"),
    ("   ", ["x"], "trecho_ausente"),
    ("a", ["abacate"], "trecho_curto"),
    ("!!", ["ola"], "trecho_curto"),
    ("x" * (MAX_TRECHO + 1), ["x" * 500], "trecho_longo"),
])
def test_refusals_are_typed_codes(trecho, msgs, codigo):
    assert conferir_trecho(trecho, msgs) == (False, codigo)


def test_only_the_last_n_messages_are_searched():
    msgs = ["quero comprar", "ola", "bom dia", "tudo bem"]
    assert conferir_trecho("quero comprar", msgs, ultimas=4)[0] is True
    assert conferir_trecho("quero comprar", msgs, ultimas=3) == (False, "trecho_nao_confere")


def test_the_model_cannot_quote_its_own_words_it_only_sees_lead_messages():
    # the caller passes LEAD messages only; text the model wrote is simply absent
    assert conferir_trecho("qual seu orcamento", ["tenho 400 mil"]) == (False, "trecho_nao_confere")


def test_joined_window_does_not_invent_text_across_non_adjacent_gaps():
    assert conferir_trecho("comprar casa", ["quero comprar", "algo", "casa grande"])[0] is False
