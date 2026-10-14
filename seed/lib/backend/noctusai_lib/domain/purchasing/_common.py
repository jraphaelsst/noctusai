"""Shared plumbing: the org `Scope` (from the organ-common kit), row helpers, decimal quantities."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, ClassVar

from noctusai_lib.domain._organ_common import OrganScope, first, new_id, now_iso

from .config import PurchasingConfig
from .errors import from_refusal, invalid


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


def rpc(s: Scope, name: str, params: dict) -> dict:
    """Call a purchasing RPC and unwrap its jsonb verdict; a refusal raises, an unknown shape is loud."""
    resp = s.db.rpc(s.cfg.rpc(name), params).execute()
    payload = getattr(resp, "data", None)
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict) or "status" not in payload:
        raise RuntimeError(f"purchasing RPC {name} answered an unexpected payload: {payload!r}")
    if payload["status"] == "refused":
        raise from_refusal(payload)
    return payload


__all__ = ["Scope", "dec", "first", "new_id", "now_iso", "qty_str", "rpc"]
