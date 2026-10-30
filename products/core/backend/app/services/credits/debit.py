"""The usage debit — every minute, charge un-charged ``ai_usage`` rows to their org's wallet.

Scope: only orgs WITH a wallet, and only rows created at/after the wallet's
``charge_from`` (an org that gets a wallet tonight is never billed for last
month). Orgs without a wallet keep today's behaviour: their rows stay
``charged_credits IS NULL`` and nobody bills them.

Per row (oldest first, bounded per run):
  * wallet ``byok``   → a 0-credit ``usage_debit`` with ``source='byok'`` (the
    org paid its own provider; the row is stamped 0 and never re-read);
  * otherwise         → priced by `pricing.price_usage` at the row's own PTAX,
    ``usage_debit`` of ``-credits`` with ``source='usage'``.

Idempotent by construction: ``credit_apply_entry`` refuses a second debit of
the same ``ai_usage_id`` (``duplicate``) and skips a row already stamped
(``already_charged``); a crash between rows just leaves the rest for the
next minute. A row that cannot be priced (no pricing version) stops the run
LOUDLY — it is never stamped 0.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.services.billing_context import BillingContext
from app.services.credits import wallets
from app.services.credits.ledger import CreditEntryInput
from app.services.credits.pricing import load_pricing, price_usage

logger = logging.getLogger(__name__)

BATCH_PER_ORG = 500
_USAGE_COLUMNS = "id,org_id,product,feature,provider,model,cost_usd,cost_brl,fx_rate,created_at,charged_credits"


@dataclass
class DebitReport:
    orgs: int = 0
    rows: int = 0
    applied: int = 0
    duplicates: int = 0
    byok: int = 0
    credits: Decimal = Decimal(0)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"orgs": self.orgs, "rows": self.rows, "applied": self.applied,
                "duplicates": self.duplicates, "byok": self.byok, "credits": float(self.credits),
                "errors": self.errors}


def _pending_rows(db: Any, org_id: str, charge_from: str, limit: int) -> list[dict[str, Any]]:
    return (
        db.table("ai_usage").select(_USAGE_COLUMNS)
        .eq("org_id", org_id)
        .is_("charged_credits", "null")
        .gte("created_at", charge_from)
        .order("id")
        .limit(limit)
        .execute()
        .data
        or []
    )


def run_debit(ctx: BillingContext, *, batch_per_org: int = BATCH_PER_ORG) -> DebitReport:
    report = DebitReport()
    wallet_rows = ctx.db.table(wallets.WALLETS).select("org_id,mode,charge_from").execute().data or []
    if not wallet_rows:
        return report
    pricing = load_pricing(ctx.db, at=ctx.clock())
    for wallet in wallet_rows:
        org_id = str(wallet["org_id"])
        report.orgs += 1
        byok = wallet.get("mode") == "byok"
        for row in _pending_rows(ctx.db, org_id, str(wallet["charge_from"]), batch_per_org):
            report.rows += 1
            try:
                if byok:
                    entry = CreditEntryInput(
                        org_id=org_id, kind="usage_debit", credits=Decimal(0), source="byok",
                        product=row.get("product"), feature=row.get("feature"),
                        brl_amount=Decimal(0), usd_amount=Decimal(str(row.get("cost_usd") or 0)),
                        provider_cost_brl=Decimal(str(row.get("cost_brl") or 0)),
                        fx_rate=Decimal(str(row["fx_rate"])), pricing_version=pricing.version,
                        ai_usage_id=int(row["id"]),
                    )
                else:
                    priced = price_usage(row.get("cost_usd") or 0, row["fx_rate"], pricing)
                    entry = CreditEntryInput(
                        org_id=org_id, kind="usage_debit", credits=-priced.credits, source="usage",
                        product=row.get("product"), feature=row.get("feature"),
                        brl_amount=priced.price_brl, usd_amount=Decimal(str(row.get("cost_usd") or 0)),
                        provider_cost_brl=Decimal(str(row.get("cost_brl") or priced.provider_cost_brl)),
                        fx_rate=Decimal(str(row["fx_rate"])), pricing_version=pricing.version,
                        ai_usage_id=int(row["id"]),
                        detail={"provider": row.get("provider"), "model": row.get("model")},
                    )
                result = wallets.apply(ctx, entry)
            except Exception as exc:  # noqa: BLE001 — one bad row must not stall the org; reported + logged
                msg = f"ai_usage {row.get('id')} (org {org_id}): {exc}"
                logger.error("credits.debit: %s", msg)
                report.errors.append(msg)
                break  # keep order: the next run retries this row first
            if result.status == "applied":
                report.applied += 1
                report.credits += -entry.credits
                if byok:
                    report.byok += 1
            else:
                report.duplicates += 1
    return report


__all__ = ["BATCH_PER_ORG", "DebitReport", "run_debit"]
