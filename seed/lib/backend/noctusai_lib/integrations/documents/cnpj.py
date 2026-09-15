"""CNPJ — normalize and verify a Brazilian company registration number.

Sibling of `cpf.py`: the same "a document that can verify itself" argument.
Two of a CNPJ's fourteen characters are a mod-11 function of the other twelve,
so a typo, a transposition or a CPF pasted into a CNPJ field is caught at the
boundary instead of being printed into a contract.

🔴 ALPHANUMERIC CNPJ (Receita Federal, IN RFB nº 2.229/2024)
-------------------------------------------------------------
From July 2026 new CNPJs may carry letters A–Z in the first twelve positions;
the two check digits stay numeric. The check-digit algorithm is unchanged
except that each character's value is `ord(char) - 48` — which is the plain
digit value for `0`–`9`, so every numeric CNPJ ever issued validates exactly as
before. A validator that only accepts digits would refuse legitimate companies
registered after the cut-over, which is why this one does not.
"""
from __future__ import annotations

import re
from typing import Optional

_PESOS_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

_FORMATO = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")


def normalize(value: Optional[str]) -> str:
    """Uppercased, with the usual punctuation (`.`, `/`, `-`, spaces) removed.

    Only punctuation is stripped — any other character survives so that
    `is_valid` refuses it rather than silently dropping it into a valid-looking
    fourteen-character string.
    """
    return re.sub(r"[.\-/\s]", "", value or "").upper()


def _digito(base: str, pesos: tuple[int, ...]) -> int:
    soma = sum((ord(c) - 48) * p for c, p in zip(base, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def is_valid(value: Optional[str]) -> bool:
    """Do this CNPJ's two check digits verify? Accepts numeric and
    alphanumeric CNPJs, punctuated or not. Rejects the numeric repdigit strings
    (`00000000000000` … `99999999999999`): some satisfy the arithmetic and none
    are real registrations — they are placeholder data, same reasoning as
    `cpf.is_valid`."""
    s = normalize(value)
    if not _FORMATO.match(s):
        return False
    if s.isdigit() and s == s[0] * 14:
        return False
    dv1 = _digito(s[:12], _PESOS_DV1)
    dv2 = _digito(s[:12] + str(dv1), _PESOS_DV2)
    return s[12:] == f"{dv1}{dv2}"


def format_cnpj(value: Optional[str]) -> Optional[str]:
    """`11222333000181` → `11.222.333/0001-81`. None when it is not fourteen
    characters of CNPJ shape (validity is `is_valid`'s job, not this one's)."""
    s = normalize(value)
    if not _FORMATO.match(s):
        return None
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"


__all__ = ["format_cnpj", "is_valid", "normalize"]
