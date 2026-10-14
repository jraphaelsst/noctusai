"""Fiscal-field validators -- pure functions, one place (service, CSV import and tests share them).

Every rule here is FORMAT-level; what is and is not verifiable offline is spelled out per field in
`ITEMS.md` (sources cited there). Each `normalize_*` returns the canonical stored form, or raises
`ItemsError` (422, with the field name and a stable pt-BR code).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .errors import (
    CEST_INVALIDO,
    CFOP_INVALIDO,
    GTIN_INVALIDO,
    NCM_INVALIDO,
    ORIGEM_INVALIDA,
    SKU_INVALIDO,
    invalid,
)

#: GS1 trade-item number lengths: GTIN-8, -12 (UPC-A), -13 (EAN-13), -14.
GTIN_LENGTHS = (8, 12, 13, 14)
SKU_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$")
#: CFOP first digit: 1/2/3 = entradas (UF / outra UF / exterior), 5/6/7 = saídas (idem).
CFOP_FIRST_DIGITS = "123567"
ORIGEM_MIN, ORIGEM_MAX = 0, 8


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _digits_only(value: Any, *, separators: str) -> Optional[str]:
    """`value` with the printed-form separators dropped, or None when anything else is left."""
    text = str(value).strip()
    stripped = re.sub(f"[{re.escape(separators)}\\s]", "", text)
    return stripped if stripped.isdigit() else None


def normalize_sku(value: Any) -> str:
    """SKU: letters/digits/`._/-`, up to 64 chars, stored UPPER-CASED (so uniqueness is case-insensitive by construction)."""
    text = "" if value is None else str(value).strip()
    if not SKU_PATTERN.match(text):
        raise invalid("sku", "SKU inválido: use letras, números e . _ / - (até 64 caracteres).", SKU_INVALIDO)
    return text.upper()


def normalize_ncm(value: Any) -> Optional[str]:
    """NCM: 8 digits (printed `8471.30.19`); the chapter (first 2 digits) is 01..97."""
    if _blank(value):
        return None
    digits = _digits_only(value, separators=".")
    if digits is None or len(digits) != 8 or not 1 <= int(digits[:2]) <= 97:
        raise invalid("ncm", "NCM inválido: informe 8 dígitos (capítulo 01 a 97).", NCM_INVALIDO)
    return digits


def normalize_cest(value: Any) -> Optional[str]:
    """CEST: 7 digits (printed `01.001.00` = segmento 2 + item 3 + especificação 2)."""
    if _blank(value):
        return None
    digits = _digits_only(value, separators=".")
    if digits is None or len(digits) != 7:
        raise invalid("cest", "CEST inválido: informe 7 dígitos.", CEST_INVALIDO)
    return digits


def normalize_cfop(value: Any) -> Optional[str]:
    """CFOP: 4 digits (printed `5.102`), first digit in 1,2,3 (entrada) or 5,6,7 (saída)."""
    if _blank(value):
        return None
    digits = _digits_only(value, separators=".")
    if digits is None or len(digits) != 4 or digits[0] not in CFOP_FIRST_DIGITS:
        raise invalid("cfop_default", "CFOP inválido: 4 dígitos iniciando em 1, 2, 3, 5, 6 ou 7.", CFOP_INVALIDO)
    return digits


def normalize_origem(value: Any) -> Optional[int]:
    """Origem da mercadoria (ICMS): integer 0..8."""
    if _blank(value):
        return None
    if isinstance(value, bool):
        raise invalid("origem", "Origem inválida: use um número de 0 a 8.", ORIGEM_INVALIDA)
    try:
        number = int(str(value).strip())
    except ValueError:
        raise invalid("origem", "Origem inválida: use um número de 0 a 8.", ORIGEM_INVALIDA) from None
    if not ORIGEM_MIN <= number <= ORIGEM_MAX:
        raise invalid("origem", "Origem inválida: use um número de 0 a 8.", ORIGEM_INVALIDA)
    return number


def gtin_check_digit(body: str) -> int:
    """GS1 mod-10 check digit of the digits BEFORE the check digit (weights 3,1,3,1... from the right)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def is_valid_gtin(digits: str) -> bool:
    return (
        digits.isdigit()
        and len(digits) in GTIN_LENGTHS
        and gtin_check_digit(digits[:-1]) == int(digits[-1])
    )


def normalize_gtin(value: Any) -> Optional[str]:
    """GTIN/EAN: 8, 12, 13 or 14 digits with a correct GS1 check digit."""
    if _blank(value):
        return None
    digits = _digits_only(value, separators="-")
    if digits is None or not is_valid_gtin(digits):
        raise invalid("gtin", "GTIN/EAN inválido: confira os dígitos (8, 12, 13 ou 14) e o dígito verificador.", GTIN_INVALIDO)
    return digits


__all__ = [
    "CFOP_FIRST_DIGITS",
    "GTIN_LENGTHS",
    "ORIGEM_MAX",
    "ORIGEM_MIN",
    "SKU_PATTERN",
    "gtin_check_digit",
    "is_valid_gtin",
    "normalize_cest",
    "normalize_cfop",
    "normalize_gtin",
    "normalize_ncm",
    "normalize_origem",
    "normalize_sku",
]
