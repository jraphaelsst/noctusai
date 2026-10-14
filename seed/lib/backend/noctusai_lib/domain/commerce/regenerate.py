"""Regenerate payment (the buyer's "gerar novo pagamento", CONTRACT §2.4 / D35).

Public, by order token. Rules:

* allowed from `expired` / `failed` (-> `pending_payment` via RETRY) and from `pending_payment`
  (a METHOD SWITCH: a new attempt, NO status change; the same method with a live charge just returns it);
* the claim is ONE conditional UPDATE on `(status, charge_attempts)` that also enforces the cap
  (`MAX_ATTEMPTS` = 5) and the spacing (`MIN_SPACING_SECONDS` = 60) -- a single atomic statement, so two
  concurrent calls cannot both create a charge (the loser gets 409 `pedido_alterado`; cap / spacing => 429
  `muitas_tentativas`). An attempt claimed is an attempt spent, even if the gateway then refuses;
* the previous charge is CANCELLED first; if that fails the call is refused with 409 `cobranca_anterior_ativa`
  -- never a second live charge. A charge already paid is not cancelled (409, the webhook will settle it);
* if a superseded attempt is paid anyway (late Pix / boleto) the webhook records it (`webhook.py`).

Closes `NOC-REMEDIATE[commerce-regenerate-payment]` and (with `orders.cancel_order`) `[commerce-gateway-cancel]`.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable, Mapping, Optional

from noctusai_lib.integrations.payments.errors import PaymentGatewayError

from . import checkout as checkout_svc
from .checkout import public_pix, split_for
from ._common import first, now, now_iso, tbl
from .config import CommerceConfig
from .customers import get_customer
from .errors import CommerceError, GatewayNotConfigured, not_found
from .gateway import GATEWAY_NAME, CheckoutGateway
from .money import parse_ts
from .order_charges import cancel_gateway_charge, current_attempt, ensure_attempt_row, insert_attempt, set_attempt_status
from .order_state import OrderEvent
from .orders import StaleOrder, append_event, apply_transition, get_order_by_token
from .types import ChargeAttemptStatus, OrderEventSource, OrderStatus, PaymentMethod

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
MIN_SPACING_SECONDS = 60

_ORDERS = "commerce_orders"
_PAYABLE = (OrderStatus.PENDING_PAYMENT.value, OrderStatus.EXPIRED.value, OrderStatus.FAILED.value)


def _not_payable() -> CommerceError:
    return CommerceError("pedido_nao_pagavel", "Este pedido não pode mais ser pago por aqui.", 409)


def _view(order: Mapping[str, Any]) -> dict:
    return {
        "status": order["status"],
        "checkout_url": order.get("checkout_url"),
        "pix_qr": order.get("pix_qr"),
        "expires_at": order.get("expires_at"),
    }


def _claim(db: Any, org_id: Any, order: Mapping[str, Any], attempts: int) -> dict:
    """Atomically reserve attempt `attempts + 1`; refuses by cause when someone else got there / the cap / the spacing."""
    moment = now()
    patch = {"charge_attempts": attempts + 1, "last_charge_attempt_at": moment.isoformat()}
    claimed = first(
        tbl(db, _ORDERS)
        .update(patch)
        .eq("org_id", str(org_id))
        .eq("id", str(order["id"]))
        .eq("status", order["status"])
        .eq("charge_attempts", attempts)
        .lt("charge_attempts", MAX_ATTEMPTS)
        .lte("last_charge_attempt_at", (moment - timedelta(seconds=MIN_SPACING_SECONDS)).isoformat())
        .execute()
    )
    if claimed is not None:
        return claimed
    fresh = first(tbl(db, _ORDERS).select("*").eq("org_id", str(org_id)).eq("id", str(order["id"])).limit(1).execute()) or {}
    if fresh.get("status") == order["status"] and int(fresh.get("charge_attempts") or 0) == attempts:
        if attempts >= MAX_ATTEMPTS:
            raise CommerceError("muitas_tentativas", "Limite de tentativas de pagamento atingido. Fale com a loja.", 429)
        raise CommerceError("muitas_tentativas", "Aguarde um minuto antes de gerar um novo pagamento.", 429)
    raise CommerceError("pedido_alterado", "O pedido mudou enquanto você agia. Recarregue a página.", 409)


def regenerate_payment(
    db: Any,
    org_id: Any,
    cfg: CommerceConfig,
    gateway: CheckoutGateway,
    token: str,
    *,
    payment_method: str,
    installments: Optional[int],
    order_url_for: Callable[[str], str],
) -> dict:
    """Create a new payment attempt for the order behind `token`; returns `{status, checkout_url, pix_qr, expires_at}`."""
    order = get_order_by_token(db, org_id, token)
    if order is None:
        raise not_found("Pedido")
    if order["status"] not in _PAYABLE:
        raise _not_payable()
    method = PaymentMethod(payment_method).value
    count = checkout_svc.parse_installments(method, installments)
    charged = checkout_svc.charged_total(db, org_id, method, count, int(order["total_cents"]))

    rows = ensure_attempt_row(db, org_id, order)
    current = current_attempt(rows, order)
    moment = now()
    expires = parse_ts(order.get("expires_at"))
    if order["status"] == OrderStatus.PENDING_PAYMENT.value:
        live = expires is None or expires > moment
        if live and current is not None and current["payment_method"] == method and int(current["installment_count"]) == count:
            return _view(order)  # same method, charge still payable: nothing to create
        if not live:
            try:
                order = apply_transition(db, org_id, order, OrderEvent.EXPIRED, source=OrderEventSource.SYSTEM, reason="prazo de pagamento esgotado")
            except StaleOrder as exc:
                raise CommerceError("pedido_alterado", "O pedido mudou enquanto você agia. Recarregue a página.", 409) from exc

    try:
        hosted = gateway.hosted_checkout(org_id)
    except GatewayNotConfigured as exc:
        logger.error("commerce regenerate: gateway not configured (org=%s): %s", org_id, exc)
        raise CommerceError("pagamento_indisponivel", "O pagamento não está disponível nesta loja agora.", 503) from exc
    customer = get_customer(db, org_id, order["customer_id"])
    if customer.get("anonymized_at") or not customer.get("doc"):
        raise _not_payable()

    attempts = max(int(order.get("charge_attempts") or 0), len(rows))
    claimed = _claim(db, org_id, order, attempts)
    attempt_no = int(claimed["charge_attempts"])

    # 1) EVERY earlier attempt that is not paid / cancelled must be provably dead BEFORE a second charge exists:
    #    the gateway keeps an overdue boleto / Pix payable, so an `expired` row is still a live charge.
    for earlier in rows:
        if earlier["status"] in (ChargeAttemptStatus.PAID.value, ChargeAttemptStatus.CANCELLED.value):
            continue
        if earlier["status"] == ChargeAttemptStatus.FAILED.value:
            continue  # a charge that never existed at the gateway
        cancel_gateway_charge(gateway, org_id, earlier["gateway_charge_id"])  # 409 cobranca_anterior_ativa when it cannot
        set_attempt_status(db, org_id, earlier["id"], ChargeAttemptStatus.CANCELLED)

    # 2) the new charge.
    wallet, percent, fee_cents = split_for(db, org_id, gateway, charged)
    buyer = {"email": customer["email"], "name": customer.get("name") or customer["email"], "doc": customer["doc"]}
    try:
        session = checkout_svc.open_gateway_charge(
            hosted, cfg, order_id=str(order["id"]), customer_id=str(customer["id"]), buyer=buyer, method=method,
            charged_cents=charged, currency=order["currency"], installments=count,
            return_url=order_url_for(order["token"]), wallet=wallet, percent=percent,
        )
    except PaymentGatewayError as exc:
        logger.error("commerce regenerate: gateway refused order=%s status=%s code=%s", order["id"], exc.status, exc.code)
        raise CommerceError("pagamento_falhou", "Não foi possível iniciar o pagamento agora. Tente novamente em instantes.", 502) from exc

    pix = public_pix(session.pix_qr)
    expires_at = (moment + timedelta(hours=cfg.order_expiry_hours)).isoformat()
    insert_attempt(
        db, org_id, order["id"], attempt=attempt_no, gateway=GATEWAY_NAME, gateway_charge_id=session.id_at_gateway,
        payment_method=method, installment_count=count, amount_cents=charged,
        checkout_url=session.checkout_url, pix_qr=pix, due_at=expires_at,
    )
    extra = {
        "gateway_charge_id": session.id_at_gateway, "checkout_url": session.checkout_url, "pix_qr": pix,
        "payment_method": method, "platform_fee_cents": fee_cents, "expires_at": expires_at,
    }
    try:
        if order["status"] == OrderStatus.PENDING_PAYMENT.value:  # method switch: no status change, but never silent
            saved = first(
                tbl(db, _ORDERS).update({**extra, "updated_at": now_iso()})
                .eq("org_id", str(org_id)).eq("id", str(order["id"])).eq("status", OrderStatus.PENDING_PAYMENT.value).execute()
            )
            if saved is None:
                raise StaleOrder(f"order {order['id']} is no longer pending_payment")
            append_event(
                db, org_id, order["id"], from_status=OrderStatus.PENDING_PAYMENT.value, to_status=OrderStatus.PENDING_PAYMENT.value,
                source=OrderEventSource.CHECKOUT, reason=f"forma de pagamento alterada para {method} (tentativa {attempt_no})",
            )
        else:
            saved = apply_transition(
                db, org_id, order, OrderEvent.RETRY, source=OrderEventSource.CHECKOUT,
                reason=f"novo pagamento gerado (tentativa {attempt_no})", extra=extra,
            )
    except StaleOrder as exc:
        # The charge exists and its row is recorded: the webhook attributes a payment to it. Say so loudly.
        logger.error("commerce regenerate: order=%s moved while attaching attempt %s (charge=%s)", order["id"], attempt_no, session.id_at_gateway)
        raise CommerceError("pedido_alterado", "O pedido mudou enquanto você agia. Recarregue a página.", 409) from exc
    return _view(saved)


__all__ = ["MAX_ATTEMPTS", "MIN_SPACING_SECONDS", "regenerate_payment"]
