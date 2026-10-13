"""Coupons -- percent or fixed (integer cents), optional window + usage cap (D29).

Money math is INTEGER cents end to end: a percent discount is
`subtotal * value // 100` (floor -- the shop never gives away a fractional cent),
a fixed discount is `min(value, subtotal)`. A coupon that would take the total to
zero is refused (`total_zero`): free orders have no gateway charge and are out of
P3's scope (NOC-REMEDIATE[commerce-free-orders]).

`code` is stored UPPERCASE so uniqueness (`lower(code)` index) and lookup are a
plain equality -- never an ILIKE, whose `_` is a wildcard and codes may contain `_`.
"""
# NOC-REMEDIATE[commerce-free-orders]: a 100%-off / zero-total order has no gateway charge to create; refused as `total_zero` until a free-order path (skip the gateway, go straight to paid) is designed with the fulfillment phase. — 2026-10-12
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import first, get_row, new_id, now, now_iso, tbl
from .errors import conflict, invalid, not_found
from .types import CouponKind

logger = logging.getLogger(__name__)

_COUPONS = "commerce_coupons"

#: Stable machine reasons the quote returns as `coupon_error`.
NAO_ENCONTRADO = "nao_encontrado"
INATIVO = "inativo"
AINDA_NAO_VALE = "ainda_nao_vale"
EXPIRADO = "expirado"
ESGOTADO = "esgotado"
TOTAL_ZERO = "total_zero"


def normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _parse(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def compute_discount(kind: str, value: int, subtotal_cents: int) -> int:
    """Integer-cents discount for `subtotal_cents`; never exceeds the subtotal."""
    if kind == CouponKind.PERCENT.value:
        return min(subtotal_cents, (subtotal_cents * int(value)) // 100)
    if kind == CouponKind.FIXED.value:
        return min(subtotal_cents, int(value))
    raise ValueError(f"unknown coupon kind {kind!r}")


# ─── staff CRUD ──────────────────────────────────────────────────────────


def _get_by_code(db: Any, org_id: Any, code: str) -> Optional[dict]:
    resp = tbl(db, _COUPONS).select("*").eq("org_id", str(org_id)).eq("code", normalize_code(code)).limit(1).execute()
    return first(resp)


def list_coupons(db: Any, org_id: Any) -> list[dict]:
    rows = paged_rows(db, _COUPONS, org_id)
    return sorted(rows, key=lambda r: str(r.get("created_at", "")), reverse=True)


def create_coupon(db: Any, org_id: Any, data: Mapping[str, Any]) -> dict:
    code = normalize_code(str(data["code"]))
    if _get_by_code(db, org_id, code) is not None:
        raise conflict("cupom_ja_existe", "Já existe um cupom com este código.")
    stamp = now_iso()
    row = {
        "id": new_id(),
        "org_id": str(org_id),
        "code": code,
        "kind": getattr(data["kind"], "value", data["kind"]),
        "value": int(data["value"]),
        "starts_at": _iso(data.get("starts_at")),
        "ends_at": _iso(data.get("ends_at")),
        "max_uses": data.get("max_uses"),
        "uses_count": 0,
        "active": bool(data.get("active", True)),
        "created_at": stamp,
        "updated_at": stamp,
    }
    try:
        return first(tbl(db, _COUPONS).insert(row).execute()) or row
    except Exception as exc:  # noqa: BLE001 - narrowed below
        if is_unique_violation(exc):
            raise conflict("cupom_ja_existe", "Já existe um cupom com este código.") from exc
        raise


def update_coupon(db: Any, org_id: Any, coupon_id: Any, changes: Mapping[str, Any]) -> dict:
    current = get_row(db, _COUPONS, org_id, coupon_id)
    if current is None:
        raise not_found("Cupom")
    patch: dict[str, Any] = {}
    for key in ("kind", "value", "starts_at", "ends_at", "max_uses", "active"):
        if key in changes:
            value = getattr(changes[key], "value", changes[key])
            patch[key] = _iso(value)
    if "code" in changes and changes["code"]:
        code = normalize_code(str(changes["code"]))
        other = _get_by_code(db, org_id, code)
        if other is not None and str(other["id"]) != str(coupon_id):
            raise conflict("cupom_ja_existe", "Já existe um cupom com este código.")
        patch["code"] = code
    merged = {**current, **patch}
    if merged["kind"] == CouponKind.PERCENT.value and not 1 <= int(merged["value"]) <= 100:
        raise invalid("value", "Cupom percentual aceita valor entre 1 e 100.")
    if not patch:
        return current
    patch["updated_at"] = now_iso()
    updated = tbl(db, _COUPONS).update(patch).eq("org_id", str(org_id)).eq("id", str(coupon_id)).execute()
    return first(updated) or {**current, **patch}


def delete_coupon(db: Any, org_id: Any, coupon_id: Any) -> None:
    if get_row(db, _COUPONS, org_id, coupon_id) is None:
        raise not_found("Cupom")
    tbl(db, _COUPONS).delete().eq("org_id", str(org_id)).eq("id", str(coupon_id)).execute()


# ─── checkout use ────────────────────────────────────────────────────────


def check_coupon(db: Any, org_id: Any, code: str, subtotal_cents: int, *, at: Optional[datetime] = None) -> tuple[Optional[dict], int, Optional[str]]:
    """Validate `code` against this org's coupons for a `subtotal_cents` cart.

    Returns `(coupon, discount_cents, error)`. On ANY refusal `coupon` is None,
    the discount is 0 and `error` is one of the module's reason constants -- the
    quote shows the buyer the reason without failing the whole quote.
    """
    coupon = _get_by_code(db, org_id, code)
    if coupon is None:
        return None, 0, NAO_ENCONTRADO
    if not coupon.get("active"):
        return None, 0, INATIVO
    moment = at or now()
    starts, ends = _parse(coupon.get("starts_at")), _parse(coupon.get("ends_at"))
    if starts and moment < starts:
        return None, 0, AINDA_NAO_VALE
    if ends and moment >= ends:
        return None, 0, EXPIRADO
    max_uses = coupon.get("max_uses")
    if max_uses is not None and int(coupon.get("uses_count", 0)) >= int(max_uses):
        return None, 0, ESGOTADO
    discount = compute_discount(coupon["kind"], int(coupon["value"]), subtotal_cents)
    if discount >= subtotal_cents:
        return None, 0, TOTAL_ZERO
    return coupon, discount, None


def reserve_use(db: Any, org_id: Any, coupon: Mapping[str, Any], *, attempts: int = 3) -> bool:
    """Count one use, optimistically (`WHERE uses_count = <seen>`), re-checking the
    cap on every retry. False when the cap was reached by a concurrent order."""
    current = dict(coupon)
    for _ in range(attempts):
        seen = int(current.get("uses_count", 0))
        max_uses = current.get("max_uses")
        if max_uses is not None and seen >= int(max_uses):
            return False
        updated = (
            tbl(db, _COUPONS)
            .update({"uses_count": seen + 1, "updated_at": now_iso()})
            .eq("org_id", str(org_id))
            .eq("id", str(current["id"]))
            .eq("uses_count", seen)
            .execute()
        )
        if updated.data:
            return True
        fresh = get_row(db, _COUPONS, org_id, current["id"])
        if fresh is None:
            return False
        current = fresh
    logger.warning("commerce coupon use contention exceeded %s attempts (coupon=%s)", attempts, coupon.get("id"))
    return False


def release_use(db: Any, org_id: Any, coupon: Mapping[str, Any], *, attempts: int = 3) -> None:
    """Give back a reserved use (the charge it was reserved for failed). Best effort,
    optimistic like `reserve_use`; contention beyond `attempts` is logged, not hidden."""
    for _ in range(attempts):
        fresh = get_row(db, _COUPONS, org_id, coupon["id"])
        if fresh is None or int(fresh.get("uses_count", 0)) <= 0:
            return
        seen = int(fresh["uses_count"])
        updated = (
            tbl(db, _COUPONS)
            .update({"uses_count": seen - 1, "updated_at": now_iso()})
            .eq("org_id", str(org_id))
            .eq("id", str(coupon["id"]))
            .eq("uses_count", seen)
            .execute()
        )
        if updated.data:
            return
    logger.warning("commerce coupon release contention exceeded %s attempts (coupon=%s)", attempts, coupon.get("id"))


__all__ = [
    "AINDA_NAO_VALE",
    "ESGOTADO",
    "EXPIRADO",
    "INATIVO",
    "NAO_ENCONTRADO",
    "TOTAL_ZERO",
    "check_coupon",
    "compute_discount",
    "create_coupon",
    "delete_coupon",
    "list_coupons",
    "normalize_code",
    "release_use",
    "reserve_use",
    "update_coupon",
]
