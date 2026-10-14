"""Items vocabulary. `str` Enums: a value serialises as its bare string and equals the literal the
frontend organ mirrors. Renaming a member is a wire-contract change, never a refactor.
"""
from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class ItemType(_StrEnum):
    """What an item IS. A vertical-seed seam: extend via `ItemsConfig.extra_item_types`."""

    GOODS = "goods"
    SERVICE = "service"
    RAW_MATERIAL = "raw_material"
    ASSET = "asset"


class Unit(_StrEnum):
    """Unit of measure (commercial unit). Codes are the common Brazilian NF-e `uCom` abbreviations."""

    UN = "UN"
    KG = "KG"
    G = "G"
    L = "L"
    ML = "ML"
    M = "M"
    M2 = "M2"
    M3 = "M3"
    H = "H"
    CX = "CX"
    PCT = "PCT"


def values(enum_cls: type[Enum]) -> tuple[str, ...]:
    """The wire values of an enum, in declaration order (SQL CHECKs + parity tests)."""
    return tuple(member.value for member in enum_cls)


__all__ = ["ItemType", "Unit", "values"]
