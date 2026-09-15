"""`cnpj.is_valid` — a company registration number that verifies itself.

🔴 WHAT THESE TESTS ARE REALLY FOR
----------------------------------
Same argument as `test_cpf.py`: the check digits are the only gate between a
typo and a contract that qualifies the wrong company. So the negatives matter
as much as the positives — a transposed digit, a CPF pasted into the field,
placeholder repdigits — and so does the one positive a digits-only validator
gets wrong: the ALPHANUMERIC CNPJ Receita Federal issues since July 2026.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.cnpj import format_cnpj, is_valid, normalize

#: The classic synthetic test CNPJ — checksum-valid, not a registration.
VALIDO = "11.222.333/0001-81"
VALIDO_NU = "11222333000181"

#: Receita Federal's published alphanumeric example (IN RFB nº 2.229/2024).
ALFANUMERICO = "12.ABC.345/01DE-35"


class TestChecksum:
    def test_a_numeric_cnpj_verifies_punctuated_or_not(self):
        assert is_valid(VALIDO) is True
        assert is_valid(VALIDO_NU) is True

    def test_a_wrong_check_digit_fails(self):
        assert is_valid("11222333000182") is False

    def test_an_alphanumeric_cnpj_verifies(self):
        assert is_valid(ALFANUMERICO) is True
        assert is_valid(ALFANUMERICO.lower()) is True

    def test_an_alphanumeric_cnpj_with_a_wrong_check_digit_fails(self):
        assert is_valid("12.ABC.345/01DE-36") is False

    def test_letters_in_the_check_digits_are_refused(self):
        assert is_valid("12ABC34501DE3A") is False

    def test_repdigits_are_rejected(self):
        for d in "0123456789":
            assert is_valid(d * 14) is False

    def test_a_cpf_is_not_a_cnpj(self):
        assert is_valid("111.444.777-35") is False

    def test_empty_and_none_are_invalid(self):
        assert is_valid("") is False
        assert is_valid(None) is False

    def test_stray_characters_are_not_silently_dropped(self):
        assert is_valid("11222333000181#") is False


class TestFormatting:
    def test_normalize_strips_punctuation_and_uppercases(self):
        assert normalize(" 12.abc.345/01de-35 ") == "12ABC34501DE35"

    def test_format_numeric(self):
        assert format_cnpj(VALIDO_NU) == VALIDO

    def test_format_alphanumeric(self):
        assert format_cnpj("12abc34501de35") == ALFANUMERICO

    def test_format_refuses_wrong_shape(self):
        assert format_cnpj("123") is None
