"""A labelled address value ends at the NEXT LABEL or the end of the line —
never at an OCR double space (real 876 error, 2026-10-13: "ALPHAVILLE
RESIDENCIAL  DOIS" came back without "DOIS"). Fixtures invented."""
from __future__ import annotations

from noctusai_lib.integrations.documents.address import find_endereco


def test_double_space_inside_a_bairro_does_not_cut_it() -> None:
    texto = (
        "Endereço: ALAMEDA DAS FLORES, 100\n"
        "Bairro: ALPHAVILLE RESIDENCIAL  DOIS\n"
        "Cidade: SANTANA DE PARNAIBA\n"
        "UF: SP\n"
        "CEP: 06540-000\n"
    )
    e = find_endereco(texto)
    assert e.bairro == "ALPHAVILLE RESIDENCIAL DOIS"  # whitespace collapsed
    assert e.cidade == "SANTANA DE PARNAIBA"


def test_two_fields_on_one_line_split_at_the_second_label() -> None:
    texto = (
        "Endereço: ALAMEDA DAS FLORES, 100\n"
        "Bairro: ALPHAVILLE RESIDENCIAL  DOIS    Cidade: SANTANA DE PARNAIBA\n"
        "CEP: 06540-000   UF: SP\n"
    )
    e = find_endereco(texto)
    assert e.bairro == "ALPHAVILLE RESIDENCIAL DOIS"
    assert e.cidade == "SANTANA DE PARNAIBA"
    assert e.uf == "SP"
    assert e.cep == "06540-000"
