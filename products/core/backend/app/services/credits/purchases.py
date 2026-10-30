"""Prepaid credit purchases through the EXISTING billing gateways (no new gateway).

`start_purchase` opens a ONE-OFF charge on the owner-enabled gateway
(Asaas: PIX / boleto / card; Stripe: card) via the seed `HostedCheckout`
(``CheckoutRequest(billing_cycle=None)``), keyed by
``external_reference = "credits:<purchase id>"``. Nothing is credited here.

The gateway's paid webhook — authenticated + claimed in the `EventInbox` by
`billing_webhooks.process_event` BEFORE any side effect — lands in
`handle_asaas_payment` / `handle_stripe_checkout`, which credit the wallet
through the same `wallets.apply` path every grant and debit uses, with
``payment_ref = "<gateway>:<payment id>"`` (UNIQUE: a replayed webhook is a
no-op even past the inbox).
"""
from __future__ import annotations

import logging
from datetime import timezone
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.integrations.payments.checkout import CheckoutRequest
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.types import Money

from app.services.billing_config import GatewayNotConfigured
from app.services.billing_context import BillingContext
from app.services.billing_subscriptions import parse_ts
from app.services.credits import wallets
from app.services.credits.ledger import CreditEntryInput
from app.services.credits.pricing import brl_for_credits, load_pricing

logger = logging.getLogger(__name__)

PURCHASES = "credit_purchases"
REF_PREFIX = "credits:"
MIN_PURCHASE_CENTS = 1000  # R$ 10,00
MAX_PURCHASE_CENTS = 5_000_000  # R$ 50.000,00
_METHODS = {"asaas": ("pix", "boleto", "card", "unspecified"), "stripe": ("card",)}


def external_reference(purchase_id: str) -> str:
    return f"{REF_PREFIX}{purchase_id}"


def purchase_id_from_reference(ref: Optional[str]) -> Optional[str]:
    if ref and str(ref).startswith(REF_PREFIX):
        return str(ref)[len(REF_PREFIX):] or None
    return None


def _get(db: Any, purchase_id: str) -> Optional[dict[str, Any]]:
    rows = db.table(PURCHASES).select("*").eq("id", purchase_id).limit(1).execute().data or []
    return rows[0] if rows else None


def start_purchase(
    ctx: BillingContext,
    *,
    org_id: str,
    amount_brl: Decimal,
    gateway: str,
    billing_method: str,
    payer_email: str,
    tax_id: Optional[str],
    actor: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    if gateway not in _METHODS:
        raise wallets.CreditsError("Gateway inválido.")
    if billing_method not in _METHODS[gateway]:
        raise wallets.CreditsError(f"Meio de pagamento inválido para {gateway}.")
    if not ctx.config.gateway_enabled(gateway):
        raise wallets.CreditsError("Este meio de pagamento não está disponível.", status_code=409)
    mode = ctx.config.mode()
    if not ctx.config.gateway_ready(gateway, mode):
        raise wallets.CreditsError("Pagamento indisponível: gateway não configurado.", status_code=503)
    if gateway == "asaas" and not tax_id:
        raise wallets.CreditsError("Informe o CPF/CNPJ para pagar com Asaas.")
    cents = int((amount_brl * 100).to_integral_value())
    if not (MIN_PURCHASE_CENTS <= cents <= MAX_PURCHASE_CENTS):
        raise wallets.CreditsError("Valor fora do limite (R$ 10,00 a R$ 50.000,00).")

    wallet = wallets.get_wallet(ctx.db, org_id)
    if wallet and wallet.get("mode") == "byok":
        raise wallets.CreditsError("Esta organização usa a própria chave de IA (BYOK) — não há créditos a comprar.",
                                   status_code=409)
    orgs = ctx.db.table("organizations").select("id, nome").eq("id", org_id).limit(1).execute().data or []
    if not orgs:
        raise wallets.CreditsError("Organização não encontrada.", status_code=404)

    pricing = load_pricing(ctx.db, at=ctx.clock())
    credits = (Decimal(cents) / 100 / pricing.credit_unit_brl).quantize(Decimal("0.000001"))
    inserted = ctx.db.table(PURCHASES).insert({
        "org_id": org_id, "credits": str(credits), "amount_cents": cents, "currency": "BRL",
        "pricing_version": pricing.version, "gateway": gateway, "gateway_mode": mode,
        "billing_method": billing_method, "status": "pending", "created_by": actor,
    }).execute().data or []
    if not inserted:
        raise RuntimeError("credits: credit_purchases insert returned no row")
    purchase = inserted[0]
    ref = external_reference(str(purchase["id"]))
    request = CheckoutRequest(
        external_reference=ref,
        customer_reference=org_id,  # one gateway customer per org; the ref is per charge
        email=payer_email,
        name=orgs[0].get("nome") or org_id,
        price=Money(cents, "BRL"),
        billing_cycle=None,
        billing_method=billing_method,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"credit_purchase_id": str(purchase["id"]), "org_id": org_id},
        tax_id=tax_id,
        description=f"Créditos de IA NoctusAI ({credits.normalize():f} créditos)",
        reuse_existing=True,
    )
    try:
        session = ctx.checkout(gateway, mode).create_checkout(request)
    except (GatewayNotConfigured, PaymentGatewayError) as exc:
        ctx.db.table(PURCHASES).update({"status": "canceled", "updated_at": ctx.clock().isoformat()}).eq(
            "id", purchase["id"]).execute()
        raise wallets.CreditsError(f"Não foi possível iniciar o pagamento: {exc}", status_code=502) from exc
    ctx.db.table(PURCHASES).update({
        "gateway_charge_id": session.id_at_gateway, "checkout_url": session.checkout_url,
        "updated_at": ctx.clock().isoformat(),
    }).eq("id", purchase["id"]).execute()
    result: dict[str, Any] = {
        "purchase_id": purchase["id"], "credits": float(credits), "amount_cents": cents,
        "checkout_url": session.checkout_url, "gateway": gateway, "mode": mode, "pix_qr": None,
    }
    if session.pix_qr is not None:
        result["pix_qr"] = {"payload": session.pix_qr.payload, "encoded_image": session.pix_qr.encoded_image,
                            "expiration_date": session.pix_qr.expiration_date}
    return result


def _credit_paid(ctx: BillingContext, purchase: dict[str, Any], *, payment_ref: str, gateway: str,
                 paid_at_iso: str, gross_cents: Optional[int]) -> str:
    if gross_cents is not None and gross_cents < int(purchase["amount_cents"]):
        logger.error("credits: purchase %s paid %s cents < %s expected — not credited",
                     purchase["id"], gross_cents, purchase["amount_cents"])
        return "underpaid"
    pricing = load_pricing(ctx.db, version=int(purchase["pricing_version"]))
    credits = Decimal(str(purchase["credits"]))
    result = wallets.apply(ctx, CreditEntryInput(
        org_id=str(purchase["org_id"]), kind="purchase", credits=credits, source=gateway,
        brl_amount=brl_for_credits(credits, pricing), pricing_version=pricing.version,
        payment_ref=payment_ref, created_by=purchase.get("created_by"),
        detail={"credit_purchase_id": str(purchase["id"]), "amount_cents": int(purchase["amount_cents"])},
    ))
    if purchase.get("status") != "paid":
        ctx.db.table(PURCHASES).update({
            "status": "paid", "paid_at": paid_at_iso, "credit_entry_id": result.entry_id,
            "updated_at": ctx.clock().isoformat(),
        }).eq("id", purchase["id"]).execute()
    return result.status


def handle_asaas_payment(ctx: BillingContext, kind: str, payment: dict[str, Any]) -> Optional[tuple[str, str]]:
    """``(status, org_id)`` when the payment is a credit purchase, else None (not ours)."""
    purchase_id = purchase_id_from_reference(payment.get("externalReference"))
    if not purchase_id:
        return None
    purchase = _get(ctx.db, purchase_id)
    if purchase is None:
        return ("ignored", "")
    org_id = str(purchase["org_id"])
    payment_id = str(payment.get("id"))
    if kind in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED", "PAYMENT_RECEIVED_IN_CASH"):
        paid_at = parse_ts(payment.get("confirmedDate") or payment.get("paymentDate")) or ctx.clock()
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=timezone.utc)
        value = payment.get("value")
        gross = int((Decimal(str(value)) * 100).to_integral_value()) if value is not None else None
        return (_credit_paid(ctx, purchase, payment_ref=f"asaas:{payment_id}", gateway="asaas",
                             paid_at_iso=paid_at.isoformat(), gross_cents=gross), org_id)
    if kind in ("PAYMENT_REFUNDED", "PAYMENT_PARTIALLY_REFUNDED", "PAYMENT_CHARGEBACK_REQUESTED"):
        if purchase.get("status") != "paid":
            return ("ignored", org_id)
        credits = Decimal(str(purchase["credits"]))
        pricing = load_pricing(ctx.db, version=int(purchase["pricing_version"]))
        result = wallets.apply(ctx, CreditEntryInput(
            org_id=org_id, kind="refund", credits=-credits, source="asaas",
            brl_amount=-brl_for_credits(credits, pricing), pricing_version=pricing.version,
            payment_ref=f"asaas:{payment_id}", reason=kind,
            detail={"credit_purchase_id": purchase_id},
        ))
        ctx.db.table(PURCHASES).update({"status": "refunded", "updated_at": ctx.clock().isoformat()}).eq(
            "id", purchase_id).execute()
        return (result.status, org_id)
    if kind in ("PAYMENT_OVERDUE", "PAYMENT_DELETED"):
        if purchase.get("status") == "pending":
            ctx.db.table(PURCHASES).update({"status": "failed", "updated_at": ctx.clock().isoformat()}).eq(
                "id", purchase_id).execute()
        return ("processed", org_id)
    return ("ignored", org_id)


def handle_stripe_checkout(ctx: BillingContext, session: dict[str, Any]) -> Optional[tuple[str, str]]:
    """``checkout.session.completed`` of a credit purchase (one-off, ``mode=payment``)."""
    purchase_id = (session.get("metadata") or {}).get("credit_purchase_id")
    if not purchase_id:
        return None
    purchase = _get(ctx.db, str(purchase_id))
    if purchase is None:
        return ("ignored", "")
    org_id = str(purchase["org_id"])
    if session.get("payment_status") != "paid":
        return ("ignored", org_id)  # async methods settle later; card is paid at completion
    total = session.get("amount_total")
    return (_credit_paid(ctx, purchase, payment_ref=f"stripe:{session.get('id')}", gateway="stripe",
                         paid_at_iso=ctx.clock().isoformat(),
                         gross_cents=int(total) if total is not None else None), org_id)


def list_purchases(db: Any, org_id: str, limit: int = 20) -> list[dict[str, Any]]:
    return (
        db.table(PURCHASES)
        .select("id, credits, amount_cents, gateway, billing_method, status, checkout_url, created_at, paid_at")
        .eq("org_id", org_id).order("created_at", desc=True).limit(limit).execute().data or []
    )


__all__ = [
    "external_reference",
    "handle_asaas_payment",
    "handle_stripe_checkout",
    "list_purchases",
    "purchase_id_from_reference",
    "start_purchase",
]
