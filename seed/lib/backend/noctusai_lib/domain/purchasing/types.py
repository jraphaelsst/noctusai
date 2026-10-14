"""Purchasing vocabulary. `str` Enums: a value serialises as its bare string and feeds the SQL CHECKs.

Renaming a member is a wire-contract change, never a refactor.
"""
from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class OrderStatus(_StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


#: Statuses a receipt may be posted against.
RECEIVABLE_STATUSES = (OrderStatus.APPROVED.value, OrderStatus.SENT.value, OrderStatus.PARTIALLY_RECEIVED.value)

#: The source stamped on every stock move and AP entry this organ writes.
SOURCE = "purchasing"


def values(enum_cls: type[Enum]) -> tuple[str, ...]:
    return tuple(member.value for member in enum_cls)


__all__ = ["OrderStatus", "RECEIVABLE_STATUSES", "SOURCE", "values"]
