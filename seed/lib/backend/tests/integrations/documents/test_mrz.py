"""`mrz.py` — the shared TD1 MRZ line-2 anchor `gender.py` and `name.py`
both build on. See `mrz.py`'s own module docstring for why the check-digit
verification lives here rather than in either field parser.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.mrz import _mrz_check, line2_indices


def _linha_mrz_2(nascimento: str = "990101", validade: str = "300101") -> str:
    return (
        f"{nascimento}{_mrz_check(nascimento)}F"
        f"{validade}{_mrz_check(validade)}BRA<<<<<<<<<<<0"
    )


class TestLine2Indices:
    def test_finds_the_verified_line(self) -> None:
        texto = f"IDBRA1234567890<<<<<<<<<<<<<<<\n{_linha_mrz_2()}\nDIAS<<TAUANE<<<<<<<<"
        assert list(line2_indices(texto)) == [1]

    def test_a_broken_check_digit_is_not_an_anchor(self) -> None:
        # Same shape as a real line 2, but the birth-date check digit is
        # wrong -- must never be mistaken for a genuine MRZ block.
        texto = "9403140F3403141BRA<<<<<<<<<<<0"
        assert list(line2_indices(texto)) == []

    def test_no_mrz_at_all_is_an_empty_list(self) -> None:
        assert list(line2_indices("CERTIDAO DE CASAMENTO\nNOMES\nFULANO SILVA\n")) == []

    def test_whitespace_an_ocr_pass_inserts_is_tolerated(self) -> None:
        linha = _linha_mrz_2()
        com_espacos = f"{linha[:6]} {linha[6:7]} {linha[7:]}"
        texto = f"L1\n{com_espacos}\nL3"
        assert list(line2_indices(texto)) == [1]

    def test_empty_text_is_an_empty_list(self) -> None:
        assert list(line2_indices("")) == []
