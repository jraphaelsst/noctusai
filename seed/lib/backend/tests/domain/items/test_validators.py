"""Fiscal validators: format rules, canonical forms, stable codes."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.items import validators as v
from noctusai_lib.domain.items.errors import ItemsError

from .conftest import EAN13, GTIN8


def code(fn, value) -> str:
    with pytest.raises(ItemsError) as e:
        fn(value)
    assert e.value.status_code == 422
    return e.value.code


@pytest.mark.parametrize("raw, want", [("84713019", "84713019"), ("8471.30.19", "84713019"), (" 0101.21.00 ", "01012100"), (84713019, "84713019")])
def test_ncm_accepts_and_canonicalises(raw, want):
    assert v.normalize_ncm(raw) == want


@pytest.mark.parametrize("raw", ["8471301", "847130199", "8471.30.1X", "00012100", "98123456", "abc"])
def test_ncm_rejects(raw):
    assert code(v.normalize_ncm, raw) == "ncm_invalido"


@pytest.mark.parametrize("raw, want", [("0100100", "0100100"), ("01.001.00", "0100100")])
def test_cest_accepts(raw, want):
    assert v.normalize_cest(raw) == want


@pytest.mark.parametrize("raw", ["010010", "01001000", "01.001.0A"])
def test_cest_rejects(raw):
    assert code(v.normalize_cest, raw) == "cest_invalido"


@pytest.mark.parametrize("raw, want", [("5102", "5102"), ("5.102", "5102"), ("6.949", "6949"), ("1102", "1102"), ("3102", "3102"), ("7102", "7102")])
def test_cfop_accepts(raw, want):
    assert v.normalize_cfop(raw) == want


@pytest.mark.parametrize("raw", ["4102", "0102", "8102", "9999", "510", "51022", "5x02"])
def test_cfop_rejects(raw):
    assert code(v.normalize_cfop, raw) == "cfop_invalido"


@pytest.mark.parametrize("raw, want", [(0, 0), ("8", 8), (" 3 ", 3)])
def test_origem_accepts(raw, want):
    assert v.normalize_origem(raw) == want


@pytest.mark.parametrize("raw", [9, -1, "x", "1.5", True])
def test_origem_rejects(raw):
    assert code(v.normalize_origem, raw) == "origem_invalida"


def test_gtin_check_digit_known_values():
    # GS1 worked examples: EAN-13 7891000100103 (check 3), GTIN-8 40170725 (check 5), UPC-A 036000291452 (check 2).
    assert v.gtin_check_digit("789100010010") == 3
    assert v.gtin_check_digit("4017072") == 5
    assert v.gtin_check_digit("03600029145") == 2
    assert v.gtin_check_digit("1234567890123") == 1  # GTIN-14 body (13 digits)


@pytest.mark.parametrize("raw", [EAN13, GTIN8, "036000291452", "12345678901231", "789-1000100103"])
def test_gtin_accepts_valid_lengths(raw):
    assert v.normalize_gtin(raw) == raw.replace("-", "")


@pytest.mark.parametrize("raw", ["7891000100104", "40170726", "123456789", "7891000100", "78910001001033", "abc"])
def test_gtin_rejects_bad_digit_or_length(raw):
    assert code(v.normalize_gtin, raw) == "gtin_invalido"


@pytest.mark.parametrize("fn", [v.normalize_ncm, v.normalize_cest, v.normalize_cfop, v.normalize_origem, v.normalize_gtin])
@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_means_unset(fn, blank):
    assert fn(blank) is None


@pytest.mark.parametrize("raw, want", [("abc-1", "ABC-1"), ("A.B_C/9", "A.B_C/9")])
def test_sku_is_upper_cased(raw, want):
    assert v.normalize_sku(raw) == want


@pytest.mark.parametrize("raw", ["", " ", "-A", "A B", "A" * 65, None, "ação"])
def test_sku_rejects(raw):
    assert code(v.normalize_sku, raw) == "sku_invalido"
