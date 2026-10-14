"""Inventory vocabulary. `str` Enums: a value serialises as its bare string and feeds the SQL CHECKs.

Renaming a member is a wire-contract change, never a refactor.
"""
from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class MoveKind(_StrEnum):
    IN = "in"
    OUT = "out"
    ADJUST = "adjust"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    RESERVE = "reserve"
    RELEASE = "release"
    COMMIT = "commit"


def values(enum_cls: type[Enum]) -> tuple[str, ...]:
    return tuple(member.value for member in enum_cls)


__all__ = ["MoveKind", "values"]
