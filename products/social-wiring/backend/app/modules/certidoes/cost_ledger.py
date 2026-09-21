"""InfoSimples spend → `public.cost_ledger` (Custos page, R2).

Each certidão consulta is a billed InfoSimples API call. This module
extracts the price InfoSimples reports on the call's own JSON response and
books one native-currency (BRL) row into the platform-wide `cost_ledger`
table (`products/core/backend/migrations/046_permissions_fx_cost_ledger.
sql`) via `get_core_client()` — `cost_ledger` lives in `public`, not
`social_wiring`, per `KB § PATTERNS/backend/backend.md § Cross-schema
reach via get_core_client()`.

PRICE FIELD — VERIFIED (2026-09-21) against the 215 real InfoSimples
responses stored in `social_wiring.certidao_resultados.api_response`: every
one carries `header.price` as a BRL decimal STRING ("0.24", "0.28") next to
`header.billable` (bool). `header.billable is False` books nothing — the
provider did not charge. `_PRICE_PATHS` keeps two defensive fallbacks, and a
response with none of them is logged at WARNING and not booked — never a
guessed number.

Never raises — booking a cost row must never break certidão issuance
itself.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

logger = logging.getLogger(__name__)

CATEGORY = "infosimples"
REFERENCE_TYPE = "certidao_consulta"

#: Candidate `(path, ...)` tuples into the InfoSimples raw JSON response,
#: tried in order. First match wins. See module docstring — `header.price`
#: is the brief's own suggestion; the other two are defensive fallbacks.
_PRICE_PATHS: tuple[tuple[str, ...], ...] = (
    ("header", "price"),
    ("header", "consumed_price"),
    ("header", "custo"),
)


def _dig(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = data
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _extract_price(raw_response: Optional[dict[str, Any]]) -> Optional[Decimal]:
    """Best-effort BRL price extraction. Returns `None` (never a guess)
    when the response carries no recognized price field or the value
    isn't numeric."""
    if not isinstance(raw_response, dict):
        return None
    for path in _PRICE_PATHS:
        value = _dig(raw_response, path)
        if value is None:
            continue
        try:
            price = Decimal(str(value))
        except (InvalidOperation, ValueError):
            logger.warning(
                "infosimples cost_ledger: field %s present but not numeric (%r)",
                ".".join(path), value,
            )
            continue
        if price < 0:
            logger.warning(
                "infosimples cost_ledger: field %s is negative (%r), skipping",
                ".".join(path), value,
            )
            continue
        return price
    return None


def book_infosimples_cost(
    core_db: Any,
    *,
    org_id: Optional[str],
    tipo: str,
    raw_response: Optional[dict[str, Any]],
    reference_id: str,
) -> bool:
    """Insert one `cost_ledger` row for a billed InfoSimples call.

    Returns True when a row was booked, False when skipped (no org_id, no
    extractable price, or the insert itself failed — every skip path logs
    why). Idempotency is NOT enforced here (unlike `storage_cost_service`'s
    daily snapshot, a certidão consulta fires once per `reference_id` by
    construction — `resultado_id` is never reused), so no pre-insert
    existence check is needed.
    """
    if not org_id:
        logger.warning(
            "infosimples cost_ledger: no org_id for consulta %s (tipo=%s) — skipping",
            reference_id, tipo,
        )
        return False
    header = raw_response.get("header") if isinstance(raw_response, dict) else None
    if isinstance(header, dict) and header.get("billable") is False:
        logger.info(
            "infosimples cost_ledger: consulta %s (tipo=%s) not billable — nothing booked",
            reference_id, tipo,
        )
        return False
    price = _extract_price(raw_response)
    if price is None:
        logger.warning(
            "infosimples cost_ledger: no recognized price field in response for "
            "consulta %s (tipo=%s) — skipping (checked %s)",
            reference_id, tipo, [".".join(p) for p in _PRICE_PATHS],
        )
        return False
    try:
        core_db.table("cost_ledger").insert({
            "org_id": org_id,
            "category": CATEGORY,
            "step": f"certidoes.{tipo}",
            "reference_type": REFERENCE_TYPE,
            "reference_id": reference_id,
            "amount_native": str(price),
            "currency": "BRL",
            "fx_pending": False,
            "amount_brl": str(price),
        }).execute()
    except Exception as exc:
        logger.warning(
            "infosimples cost_ledger: insert failed for consulta %s (tipo=%s): %s",
            reference_id, tipo, exc,
        )
        return False
    return True


__all__ = ["book_infosimples_cost", "CATEGORY", "REFERENCE_TYPE"]
