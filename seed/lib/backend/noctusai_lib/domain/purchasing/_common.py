"""Shared plumbing: the org `Scope` (from the organ-common kit), row helpers, decimal quantities."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, ClassVar

from noctusai_lib.domain._organ_common import OrganScope, first, new_id, now_iso

from .config import PurchasingConfig
from .errors import invalid


def dec(value: Any) -> Decimal:
    """A PostgREST numeric (float / str / int / None) -> exact `Decimal` (via `str`, never the float repr)."""
    if value is None or value == "":
        return Decimal(0)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def qty_str(value: Any) -> str:
    """A quantity as the string the RPC casts to `numeric` (JSON has no Decimal; a float would round)."""
    return format(dec(value), "f")


@dataclass(frozen=True)
class Scope(OrganScope):
    """`(db, cfg, org_id)` -- the unit every service function operates on (stable `id` order by default)."""

    cfg: PurchasingConfig
    default_order: ClassVar[tuple[tuple[str, bool], ...]] = (("id", False),)

    def _invalid(self, field: str, message: str, code: str) -> Exception:
        return invalid(field, message, code=code)


__all__ = ["Scope", "dec", "first", "new_id", "now_iso", "qty_str"]
