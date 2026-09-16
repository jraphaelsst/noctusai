"""PTAX (BCB venda/fechamento) persistence + BRL conversion for Core.

The seed adapter (`noctusai_lib.integrations.fx`) fetches a bulletin; this
module stores it in `public.fx_rates` (migration 046) and uses the stored
rate to convert foreign-currency amounts. A conversion with no bulletin
yet is recorded as PENDING — never priced off a default rate — and the
daily PTAX job resolves pending rows once the bulletin exists.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from noctusai_lib.integrations.fx import FxBulletinNotFoundError, FxRateAdapter, FxUpstreamError
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

logger = logging.getLogger(__name__)

PAIR = "USD/BRL"
SUPPORTED_FOREIGN = frozenset({"USD"})
_LOOKBACK_DAYS = 10


@dataclass(frozen=True)
class Conversion:
    pending: bool
    fx_rate: Optional[Decimal] = None
    fx_quote_date: Optional[date] = None

    def to_brl(self, amount: Decimal, *, places: str = "0.000001") -> Optional[Decimal]:
        if self.pending or self.fx_rate is None:
            return None
        return (amount * self.fx_rate).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _stored_rate(db: Any, on: date) -> Optional[dict[str, Any]]:
    rows = (
        db.table("fx_rates")
        .select("id, rate, quote_date")
        .eq("pair", PAIR)
        .lte("quote_date", on.isoformat())
        .gte("quote_date", (on - timedelta(days=_LOOKBACK_DAYS)).isoformat())
        .order("quote_date", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def fetch_and_store_ptax(db: Any, fx: FxRateAdapter, on: date) -> Optional[dict[str, Any]]:
    """Fetch the latest bulletin with quote_date <= `on` and store it once.

    Returns the stored row, or None when BCB has no bulletin in the
    lookback window (logged — the caller's rows stay pending).
    """
    try:
        rate = fx.get_ptax(on)
    except FxBulletinNotFoundError as exc:
        logger.info("fx_service: no PTAX bulletin for %s yet (%s)", on, exc)
        return None
    except FxUpstreamError as exc:
        logger.warning("fx_service: BCB PTAX lookup failed for %s: %s", on, exc)
        return None
    existing = (
        db.table("fx_rates")
        .select("id, rate, quote_date")
        .eq("pair", PAIR)
        .eq("quote_date", rate.quote_date.isoformat())
        .limit(1)
        .execute()
        .data
        or []
    )
    if existing:
        return existing[0]
    inserted = (
        db.table("fx_rates")
        .insert(
            {
                "pair": PAIR,
                "quote_date": rate.quote_date.isoformat(),
                "rate": str(rate.rate),
                "bulletin_at": rate.bulletin_at.isoformat(),
                "source": rate.source,
            }
        )
        .execute()
        .data
        or []
    )
    logger.info("fx_service: stored PTAX %s for %s", rate.rate, rate.quote_date)
    return inserted[0] if inserted else None


def conversion_for(db: Any, fx: Optional[FxRateAdapter], currency: str, on: date) -> Conversion:
    """The rate to price a `currency` amount incurred on `on`.

    BRL is its own conversion. A currency we have no pair for is a
    programming error (raises) — it must not be booked as pending forever.
    """
    currency = currency.upper()
    if currency == "BRL":
        return Conversion(pending=False)
    if currency not in SUPPORTED_FOREIGN:
        raise ValueError(f"fx_service: no PTAX pair for currency {currency}")
    row = _stored_rate(db, on)
    if row is None and fx is not None:
        row = fetch_and_store_ptax(db, fx, on)
    if row is None:
        return Conversion(pending=True)
    return Conversion(
        pending=False,
        fx_rate=Decimal(str(row["rate"])),
        fx_quote_date=date.fromisoformat(str(row["quote_date"])[:10]),
    )


def _created_date(row: dict[str, Any]) -> date:
    raw = str(row.get("created_at") or row.get("paid_at") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        logger.warning("fx_service: row %s has unparseable timestamp %r; pricing on today", row.get("id"), raw)
        return date.today()


def resolve_pending_cost_ledger(db: Any, fx: Optional[FxRateAdapter]) -> int:
    """Price every `cost_ledger` row still waiting for a bulletin."""
    resolved = 0
    pending = list(
        iter_paged_rows(
            lambda start, end: db.table("cost_ledger")
            .select("id, amount_native, currency, created_at")
            .eq("fx_pending", True)
            .order("id")
            .range(start, end)
            .execute()
            .data,
            label="cost_ledger fx_pending",
        )
    )
    for row in pending:
        conversion = conversion_for(db, fx, row["currency"], _created_date(row))
        if conversion.pending:
            continue
        amount = Decimal(str(row["amount_native"]))
        db.table("cost_ledger").update(
            {
                "fx_pending": False,
                "fx_rate": str(conversion.fx_rate),
                "fx_quote_date": conversion.fx_quote_date.isoformat(),
                "amount_brl": str(conversion.to_brl(amount)),
            }
        ).eq("id", row["id"]).eq("fx_pending", True).execute()
        resolved += 1
    return resolved


def resolve_pending_payments(db: Any, fx: Optional[FxRateAdapter]) -> int:
    """Price every `billing_payments` row charged in a foreign currency."""
    resolved = 0
    pending = list(
        iter_paged_rows(
            lambda start, end: db.table("billing_payments")
            .select("id, currency, gross_cents, fee_cents, created_at, paid_at")
            .eq("fx_pending", True)
            .order("id")
            .range(start, end)
            .execute()
            .data,
            label="billing_payments fx_pending",
        )
    )
    for row in pending:
        conversion = conversion_for(db, fx, row["currency"], _created_date(row))
        if conversion.pending:
            continue
        gross = Decimal(int(row["gross_cents"])) / 100
        fee = Decimal(int(row.get("fee_cents") or 0)) / 100
        db.table("billing_payments").update(
            {
                "fx_pending": False,
                "fx_rate": str(conversion.fx_rate),
                "fx_quote_date": conversion.fx_quote_date.isoformat(),
                "gross_brl": str(conversion.to_brl(gross, places="0.01")),
                "fee_brl": str(conversion.to_brl(fee, places="0.01")),
            }
        ).eq("id", row["id"]).eq("fx_pending", True).execute()
        resolved += 1
    return resolved


__all__ = [
    "Conversion",
    "PAIR",
    "conversion_for",
    "fetch_and_store_ptax",
    "resolve_pending_cost_ledger",
    "resolve_pending_payments",
]
