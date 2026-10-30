"""Shared setup for the AI credit wallet tests — `make_ctx()` + the credit ledger
seam (`BillingContext.credit_ledger = FakeCreditLedger`, the contract of the
``credit_apply_entry`` RPC over the schema-validated MockSupabaseClient)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.services.credits.ledger import FakeCreditLedger
from tests.billing_fakes import ADMIN_USER, NOW, ORG_ID, OTHER_ORG_ID, OWNER_USER, make_ctx, seed_catalog, seed_users

PRICING_V1 = {
    "id": "p1", "version": 1, "effective_from": "2026-01-01T00:00:00+00:00",
    "credit_unit_brl": "0.01", "margin": "1.0", "fx_buffer_brl": "0.10", "iof_rate": "0.035",
    "import_tax_rate": "0", "simples_rate": "0.06", "gateway_fee_rate": "0.0399", "notes": "v1",
    "created_at": "2026-01-01T00:00:00+00:00",
}


def credits_ctx(**kwargs: Any):
    ctx, fakes = make_ctx(ptax={date(2026, 9, 16): Decimal("5.00000")}, **kwargs)
    seed_catalog(fakes.db)
    seed_users(fakes.db)
    for table in ("credit_wallets", "credit_entries", "credit_purchases", "ai_usage", "notifications",
                  "fx_rates", "billing_customers"):
        fakes.db.set_table_data(table, [])
    fakes.db.set_table_data("credit_pricing", [dict(PRICING_V1)])
    fakes.db.set_table_data("org_memberships", [
        {"id": "m1", "org_id": ORG_ID, "user_id": OWNER_USER, "org_role": "owner", "status": "active"},
    ])
    ctx.credit_ledger = FakeCreditLedger(fakes.db)
    return ctx, fakes


def usage_row(i: int, *, org_id: str = ORG_ID, cost_usd: str = "1.0", product: str = "erp-imobiliario",
              feature: str = "chat", created_at: str = "2026-09-16T11:00:00+00:00", **extra: Any) -> dict[str, Any]:
    return {
        "id": i, "created_at": created_at, "org_id": org_id, "product": product, "feature": feature,
        "provider": "openai", "model": "gpt-4o-mini", "operation": "chat", "input_tokens": 1000,
        "output_tokens": 500, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": cost_usd,
        "fx_rate": "5.00000", "cost_brl": str(Decimal(cost_usd) * 5), "price_version": "t",
        "status": "ok", "charged_credits": None, **extra,
    }


def wallet_row(org_id: str = ORG_ID, **extra: Any) -> dict[str, Any]:
    return {
        "org_id": org_id, "mode": "prepaid", "balance_credits": 0, "overdraft_limit_credits": 0,
        "alert_thresholds": [0.5, 0.8, 1.0], "alert_base_credits": 0, "last_alert_threshold": 0,
        "charge_from": "2026-09-01T00:00:00+00:00", "created_at": NOW.isoformat(), "updated_at": NOW.isoformat(),
        **extra,
    }


__all__ = ["ADMIN_USER", "ORG_ID", "OTHER_ORG_ID", "OWNER_USER", "PRICING_V1", "credits_ctx", "usage_row",
           "wallet_row"]
