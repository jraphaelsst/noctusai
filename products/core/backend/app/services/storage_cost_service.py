"""Daily storage-cost snapshot → `storage_usage_snapshots` + `cost_ledger`.

Reads bytes per (bucket, org) from `public.storage_usage_by_prefix()`
(migration 050), stores the day's snapshot, and books one USD
`supabase_storage` cost row per org-attributed bucket, priced at the
admin-set `storage_price_usd_per_gb_month` and prorated to one day. The
row is converted with PTAX when a bulletin exists, else left `fx_pending`
for the PTAX job — never priced off a default rate.

Objects with no org prefix are snapshotted (the platform admin sees the
total) but not booked: `cost_ledger.org_id` is required, and inventing an
owner for them would misattribute the cost.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services import fx_service
from app.services.billing_context import BillingContext

logger = logging.getLogger(__name__)

GIB = Decimal(1024 ** 3)
CATEGORY = "supabase_storage"
REFERENCE_TYPE = "storage_usage_snapshot"


@dataclass
class StorageSnapshotReport:
    snapshot_date: str
    buckets: int = 0
    total_bytes: int = 0
    booked: int = 0
    already_booked: int = 0
    unattributed_bytes: int = 0
    skipped_reason: str = ""


def daily_cost_usd(total_bytes: int, price_per_gb_month: Decimal, on: date) -> Decimal:
    days = monthrange(on.year, on.month)[1]
    cost = Decimal(int(total_bytes)) / GIB * price_per_gb_month / Decimal(days)
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def snapshot_storage_costs(ctx: BillingContext) -> StorageSnapshotReport:
    today = ctx.clock().date()
    report = StorageSnapshotReport(snapshot_date=today.isoformat())
    price = ctx.config.storage_price_usd_per_gb_month()
    rows: list[dict[str, Any]] = ctx.db.rpc("storage_usage_by_prefix").execute().data or []

    # Idempotent per day: replace the day's snapshot wholesale.
    ctx.db.table("storage_usage_snapshots").delete().eq("snapshot_date", today.isoformat()).execute()
    if rows:
        ctx.db.table("storage_usage_snapshots").insert(
            [
                {
                    "snapshot_date": today.isoformat(),
                    "bucket_id": row["bucket_id"],
                    "org_id": row.get("org_id"),
                    "total_bytes": int(row.get("total_bytes") or 0),
                }
                for row in rows
            ]
        ).execute()
    report.buckets = len(rows)
    report.total_bytes = sum(int(r.get("total_bytes") or 0) for r in rows)
    report.unattributed_bytes = sum(int(r.get("total_bytes") or 0) for r in rows if not r.get("org_id"))

    if price is None:
        report.skipped_reason = "storage_price_usd_per_gb_month is not set"
        logger.warning("storage_cost: snapshot stored but no cost booked — %s", report.skipped_reason)
        return report

    conversion = fx_service.conversion_for(ctx.db, ctx.fx, "USD", today)
    for row in rows:
        org_id = row.get("org_id")
        size = int(row.get("total_bytes") or 0)
        if not org_id or size <= 0:
            continue
        reference_id = f"{today.isoformat()}:{row['bucket_id']}"
        exists = (
            ctx.db.table("cost_ledger")
            .select("id")
            .eq("category", CATEGORY)
            .eq("reference_type", REFERENCE_TYPE)
            .eq("reference_id", reference_id)
            .eq("org_id", org_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if exists:
            report.already_booked += 1
            continue
        amount = daily_cost_usd(size, price, today)
        entry: dict[str, Any] = {
            "org_id": org_id,
            "category": CATEGORY,
            "step": "core.storage_snapshot",
            "reference_type": REFERENCE_TYPE,
            "reference_id": reference_id,
            "amount_native": str(amount),
            "currency": "USD",
        }
        if conversion.pending:
            entry["fx_pending"] = True
        else:
            entry.update(
                {
                    "fx_pending": False,
                    "fx_rate": str(conversion.fx_rate),
                    "fx_quote_date": conversion.fx_quote_date.isoformat(),
                    "amount_brl": str(conversion.to_brl(amount)),
                }
            )
        ctx.db.table("cost_ledger").insert(entry).execute()
        report.booked += 1
    return report


__all__ = ["StorageSnapshotReport", "daily_cost_usd", "snapshot_storage_costs"]
