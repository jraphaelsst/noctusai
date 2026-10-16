"""Gateway webhook -> finance: a paid Asaas charge settles its receivable.

The receivable is found by the idempotency reference we sent (``orbity:<entry_id>`` = ``externalReference``) or by the
gateway charge id; the settlement is keyed ``(payment, asaas:<charge id>)`` so a replayed event (the inbox already
dedupes by event id; this is the second layer, e.g. CONFIRMED then RECEIVED for the same charge) settles ONCE.
Everything else a gateway can say (refund, dispute, overdue, deleted) is reported as ``ignored`` and LOGGED -- never
guessed at: those need an operator decision.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from noctusai_lib.domain.finance._common import Scope as FinanceScope
from noctusai_lib.domain.finance.accounts import get_or_create_gateway_account
from noctusai_lib.domain.finance.settlements import settle_entry
from noctusai_lib.integrations.payments.webhook_events import GatewayEvent

from app.billing import FINANCE_CFG, GATEWAY_NAME
from app.services.billing_charges import CHARGES, ChargeStore, today_br

logger = logging.getLogger(__name__)


def _cents(value: Any) -> int:
    return int(round(float(value) * 100))


def find_charge(db: Any, org_id: str, event: GatewayEvent) -> Optional[dict]:
    q = db.table(CHARGES).select("*").eq("org_id", str(org_id))
    if event.charge_id_at_gateway:
        rows = q.eq("external_id", event.charge_id_at_gateway).limit(1).execute().data or []
        if rows:
            return rows[0]
    if event.external_reference:
        rows = (db.table(CHARGES).select("*").eq("org_id", str(org_id)).eq("external_ref", event.external_reference)
                .limit(1).execute().data or [])
        if rows:
            return rows[0]
    return None


def apply_event(db: Any, org_id: str, event: GatewayEvent, *, today: Optional[date] = None) -> dict:
    """Apply one verified, first-seen event. Returns ``{"status": "settled" | "ignored" | "unknown_charge", ...}``."""
    if event.kind != "charge_paid":
        logger.info("billing webhook: %s (%s) not applied automatically", event.kind, event.detail)
        return {"status": "ignored", "kind": event.kind}
    charge = find_charge(db, org_id, event)
    if charge is None:
        logger.warning("billing webhook: paid charge %s / %s matches no receivable of org %s", event.charge_id_at_gateway, event.external_reference, org_id)
        return {"status": "unknown_charge"}
    store = ChargeStore(db)
    if not charge.get("external_id") and event.charge_id_at_gateway:
        # The webhook can beat our own bookkeeping of the create call: remember the gateway id.
        store.update_charge(org_id, charge["id"], {"external_id": event.charge_id_at_gateway, "generation_status": "generated"})
    entry = store.entry(org_id, charge["entry_id"])
    if entry is None or entry["status"] == "cancelled":
        logger.warning("billing webhook: charge %s paid but receivable %s is %s -- needs an operator", event.charge_id_at_gateway,
                       charge["entry_id"], "missing" if entry is None else "cancelled")
        return {"status": "ignored", "kind": "paid_but_cancelled"}
    payment = (event.raw or {}).get("payment") or {}
    value = _cents(payment.get("value") or 0)
    net = payment.get("netValue")
    fee = max(value - _cents(net), 0) if net is not None and value else 0
    remaining = int(entry["amount_cents"]) - int(entry.get("settled_cents") or 0)
    amount = min(value, remaining) if value else remaining
    scope = FinanceScope(db, FINANCE_CFG, str(org_id))
    account = get_or_create_gateway_account(scope, GATEWAY_NAME)
    settled_on = date.fromisoformat(str(payment.get("paymentDate") or payment.get("clientPaymentDate") or (today or today_br()).isoformat())[:10])
    result = settle_entry(scope, entry["id"], {
        "account_id": account["id"], "kind": "payment", "settled_on": settled_on.isoformat(), "amount_cents": amount,
        "fee_cents": fee if amount == value else 0, "external_ref": f"{GATEWAY_NAME}:{event.charge_id_at_gateway}",
        "method": GATEWAY_NAME,
    }) if amount > 0 else {"replayed": True}
    return {"status": "settled", "entry_id": str(entry["id"]), "replayed": bool(result.get("replayed"))}


__all__ = ["apply_event", "find_charge"]
