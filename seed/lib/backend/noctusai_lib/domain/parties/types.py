"""Parties vocabulary: the two person kinds and the roles a party can play.

`str` Enums (wire value == the literal the frontend organ mirrors). Renaming a member is a
wire-contract change, never a refactor: `values()` feeds the SQL CHECKs and the parity tests.
"""
from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class PartyKind(_StrEnum):
    """PF = pessoa física (CPF), PJ = pessoa jurídica (CNPJ)."""

    PF = "PF"
    PJ = "PJ"


class PartyRole(_StrEnum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    EMPLOYEE = "employee"
    CARRIER = "carrier"


def values(enum_cls: type[Enum]) -> tuple[str, ...]:
    """The wire values of an enum, in declaration order (SQL CHECKs + parity tests)."""
    return tuple(member.value for member in enum_cls)


__all__ = ["PartyKind", "PartyRole", "values"]
