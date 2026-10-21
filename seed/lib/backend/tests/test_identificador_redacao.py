"""`primitives.identificador_redacao` -- mask known identity values in text / structures."""
from noctusai_lib.primitives.identificador_redacao import (
    MASCARA, contem_valores, redigir_estrutura, redigir_valores,
)

CPF = "123.456.789-09"
DIG = "12345678909"


def test_value_masked_with_and_without_punctuation():
    for t in (f"cpf {CPF}", f"cpf {DIG}", "cpf 123 456 789 09", "cpf 123.456.78909"):
        assert redigir_valores(t, [DIG]) == f"cpf {MASCARA}", t


def test_only_given_values_touched_and_min_length():
    out = redigir_valores(f"tel 11987654321 cpf {CPF} cep 01310-100", [DIG])
    assert "11987654321" in out and "01310-100" in out and DIG not in out
    assert redigir_valores("123", ["123"]) == "123"
    assert redigir_valores("abc", [None, "", "  "]) == "abc"


def test_rg_case_insensitive_and_idempotent():
    assert redigir_valores("rg 12.345.678-x", ["12345678X"]) == "rg ***"
    once = redigir_valores(f"cpf {CPF}", [DIG])
    assert redigir_valores(once, [DIG]) == once


def test_estrutura_recursive_keeps_keys_and_non_strings():
    meta = {"a": [f"cpf {CPF}", {"b": DIG}], "n": 3, "ok": None, DIG: "k"}
    assert redigir_estrutura(meta, [DIG]) == {"a": [f"cpf {MASCARA}", {"b": MASCARA}], "n": 3, "ok": None, DIG: "k"}
    assert redigir_estrutura(meta, []) is meta


def test_contem_valores():
    assert contem_valores({"x": [f"cpf {CPF}"]}, [DIG])
    assert not contem_valores({"x": ["nada"]}, [DIG])
