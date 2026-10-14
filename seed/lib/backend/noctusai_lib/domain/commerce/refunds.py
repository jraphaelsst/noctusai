"""Refunds (CONTRACT §2.4 / D32) -- create under a row lock, reconcile against the gateway.

`create_refund` is a two-step protocol around the `commerce_create_refund` RPC:

    1. reconcile what the gateway already shows (a refund made in the Asaas panel) so the
       server-side refundable balance is true;
    2. RPC (one transaction, `SELECT ... FOR UPDATE` on the order): recompute the refundable
       amount = paid charge - sum(non-failed refunds), refuse a second `requested` refund
       (409 `estorno_em_andamento`), honour the `Idempotency-Key`, insert the `requested` row;
    3. `refund_charge` at the gateway -> `done` (or `failed` + 502 `estorno_falhou`);
    4. derive the order status from the totals + book the refund settlement in finance.

`reconcile_refunds` is the webhook <-> API meeting point (W2): Asaas refunds carry NO id, so a
gateway refund is matched to a row by amount + timestamp (date-granular on the Asaas side, hence
the window); a gateway refund with no row (made in the panel) becomes a `done` row with
`requested_by=NULL, reason='gateway'`. A `requested` row the gateway never confirms is closed as
`failed` so it cannot block refunds forever.

Refunding a card order paid in installments (several gateway payments, one per parcela) needs the
parcelamento-level refund, which `ChargeOperations` does not expose; it is refused with 409
`estorno_parcelado_indisponivel` (see the marker at `create_refund`) rather than refunding one parcela and leaving the
order half-refunded.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.types import GatewayCharge, Money
from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from . import finance_bridge
from ._common import first, new_id, now, now_iso, tbl
from .errors import CommerceError, GatewayNotConfigured
from .money import MoneyDeps, fire_revoked, parse_ts, rpc_json
from .money_sql import CREATE_REFUND_RPC
from .order_charges import ensure_attempt_row, paid_attempt
from .order_state import OrderEvent
from .orders import StaleOrder, apply_transition, get_order, list_items
from .types import OrderEventSource, OrderStatus, RefundStatus

logger = logging.getLogger(__name__)

_REFUNDS = "commerce_refunds"

#: A `requested` row with no gateway match older than this is closed as `failed`.
STALE_REQUESTED_AFTER = timedelta(minutes=15)
#: Asaas reports refund dates, not instants: a local row and a gateway refund within this window may be the same refund.
MATCH_WINDOW = timedelta(days=2)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_REFUNDABLE = (OrderStatus.PAID.value, OrderStatus.PARTIALLY_REFUNDED.value)


def list_refunds(db: Any, org_id: Any, order_id: Any) -> list[dict]:
    rows = paged_rows(db, _REFUNDS, org_id, eq_filters={"order_id": str(order_id)})
    return sorted(rows, key=lambda r: (str(r.get("created_at", "")), str(r["id"])))


def refunded_cents(refunds: list[dict]) -> int:
    return sum(int(r["amount_cents"]) for r in refunds if r["status"] == RefundStatus.DONE.value)


def _update(db: Any, org_id: Any, refund_id: Any, patch: Mapping[str, Any], *, only_status: Optional[str] = None) -> Optional[dict]:
    query = tbl(db, _REFUNDS).update(dict(patch)).eq("org_id", str(org_id)).eq("id", str(refund_id))
    if only_status:
        query = query.eq("status", only_status)
    return first(query.execute())


def _near(row: Mapping[str, Any], created_at: Optional[datetime]) -> bool:
    if created_at is None:
        return True
    local = parse_ts(row.get("created_at")) or _EPOCH
    return abs(local - created_at) <= MATCH_WINDOW


def reconcile_refunds(db: Any, org_id: Any, order: Mapping[str, Any], charge_row: Mapping[str, Any], gateway_charge: GatewayCharge) -> list[dict]:
    """Make `commerce_refunds` agree with `GatewayCharge.refunds`; returns the rows that BECAME `done` here."""
    rows = list_refunds(db, org_id, order["id"])
    matched: set[str] = set()
    became_done: list[dict] = []
    moment = now()
    for g in sorted(gateway_charge.refunds, key=lambda x: x.created_at or _EPOCH):
        local: Optional[dict] = None
        if g.id_at_gateway:
            local = next((r for r in rows if r.get("gateway_refund_id") == g.id_at_gateway and str(r["id"]) not in matched), None)
        if local is None:
            candidates = [
                r for r in rows
                if str(r["id"]) not in matched
                and not r.get("gateway_refund_id")
                and r["status"] in (RefundStatus.REQUESTED.value, RefundStatus.DONE.value)
                and int(r["amount_cents"]) == g.amount.amount_cents
                and _near(r, g.created_at)
            ]
            candidates.sort(key=lambda r: abs((parse_ts(r.get("created_at")) or _EPOCH) - (g.created_at or moment)))
            local = candidates[0] if candidates else None
        done = g.status == "done"
        if local is None:
            row = {
                "id": new_id(),
                "org_id": str(org_id),
                "order_id": str(order["id"]),
                "charge_id": str(charge_row["id"]),
                "amount_cents": g.amount.amount_cents,
                "reason": "gateway",
                "status": (RefundStatus.DONE if done else RefundStatus.REQUESTED).value,
                "gateway_refund_id": g.id_at_gateway,
                "idempotency_key": None,
                "requested_by": None,
                "created_at": (g.created_at or moment).isoformat(),
                "done_at": (g.created_at or moment).isoformat() if done else None,
            }
            try:
                saved = first(tbl(db, _REFUNDS).insert(row).execute()) or row
            except Exception as exc:  # noqa: BLE001 - narrowed below
                if not is_unique_violation(exc):
                    raise
                logger.warning("commerce refunds: gateway refund for order=%s collides with an existing row; left for the next sync", order["id"])
                continue
            rows.append(saved)
            matched.add(str(saved["id"]))
            if done:
                became_done.append(saved)
            continue
        matched.add(str(local["id"]))
        patch: dict[str, Any] = {}
        if g.id_at_gateway and not local.get("gateway_refund_id"):
            patch["gateway_refund_id"] = g.id_at_gateway
        if local["status"] == RefundStatus.REQUESTED.value and done:
            patch.update({"status": RefundStatus.DONE.value, "done_at": now_iso()})
        if patch:
            updated = _update(db, org_id, local["id"], patch)
            if updated and "status" in patch:
                became_done.append(updated)
    # A `requested` row the gateway does not show: gateway-origin ones vanished; ours may be a crash leftover.
    for r in rows:
        if r["status"] != RefundStatus.REQUESTED.value or str(r["id"]) in matched:
            continue
        age = moment - (parse_ts(r.get("created_at")) or moment)
        if r.get("requested_by") is None or age > STALE_REQUESTED_AFTER:
            logger.warning("commerce refunds: closing unconfirmed requested refund=%s (order=%s) as failed", r["id"], order["id"])
            _update(db, org_id, r["id"], {"status": RefundStatus.FAILED.value}, only_status=RefundStatus.REQUESTED.value)
    return became_done


def apply_refund_state(
    db: Any,
    org_id: Any,
    deps: MoneyDeps,
    order: dict,
    charge_row: Mapping[str, Any],
    *,
    source: OrderEventSource,
    newly_done: list[dict],
) -> dict:
    """Derive `partially_refunded` / `refunded` from the totals, fire `on_revoked`, book finance. Returns the order.

    Order moves only from `paid` / `partially_refunded`; a `disputed` order is left to the dispute flow.
    Finance bookings run for every `done` refund each time (idempotent), so a failed earlier attempt heals."""
    refunds = list_refunds(db, org_id, order["id"])
    total = refunded_cents(refunds)
    paid = int(charge_row["amount_cents"])
    event: Optional[OrderEvent] = None
    if order["status"] in _REFUNDABLE:
        if total >= paid:
            event = OrderEvent.REFUND
        elif total > 0 and (newly_done or order["status"] == OrderStatus.PAID.value):
            event = OrderEvent.PARTIAL_REFUND
    if event is not None:
        order = apply_transition(
            db, org_id, order, event, source=source,
            reason="reembolso total" if event is OrderEvent.REFUND else "reembolso parcial",
        )
        if event is OrderEvent.REFUND:
            deps.fulfillment.dispatch_revoked(order, list_items(db, org_id, order["id"]))
    finance_bridge.book_refunds(db, org_id, deps, order, charge_row, refunds)
    return order


def _refusal(code: str, details: Mapping[str, Any]) -> CommerceError:
    table = {
        "pedido_nao_encontrado": (404, "Pedido não encontrado."),
        "pedido_nao_reembolsavel": (409, "Este pedido não pode ser reembolsado agora."),
        "cobranca_nao_encontrada": (409, "Não há cobrança paga para reembolsar neste pedido."),
        "estorno_em_andamento": (409, "Já existe um reembolso em andamento para este pedido."),
        "valor_excede_saldo": (422, "O valor excede o saldo reembolsável do pedido."),
    }
    status, message = table.get(code, (409, "Não foi possível criar o reembolso."))
    return CommerceError(code, message, status, details=dict(details))


# NOC-REMEDIATE[commerce-installment-refund]: refund of an installment card order is refused (409 estorno_parcelado_indisponivel) -- ChargeOperations has no parcelamento-level refund; destination: payments organ `refund_installment` (P9 back office) — 2026-10-14
async def create_refund(
    db: Any,
    org_id: Any,
    deps: MoneyDeps,
    order_id: Any,
    *,
    amount_cents: Optional[int],
    reason: str,
    requested_by: Any,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Refund `amount_cents` (None = everything still refundable) of a paid order. Returns the refund row."""
    order = get_order(db, org_id, order_id)
    rows = ensure_attempt_row(db, org_id, order)
    paid_row = paid_attempt(rows)
    if paid_row is not None and int(paid_row["installment_count"]) > 1:
        raise CommerceError(
            "estorno_parcelado_indisponivel",
            "Reembolso de compra parcelada ainda não está disponível; faça o estorno no painel do gateway.",
            409,
        )
    try:
        ops = deps.gateway.charge_operations(org_id)
    except GatewayNotConfigured as exc:
        logger.error("commerce refund: gateway not configured (org=%s): %s", org_id, exc)
        raise CommerceError("pagamento_indisponivel", "O gateway de pagamento não está configurado.", 503) from exc

    if paid_row is not None and order["status"] in _REFUNDABLE:
        try:
            gw = ops.get_charge(paid_row["gateway_charge_id"])
        except PaymentGatewayError as exc:
            logger.error("commerce refund: could not read the charge (order=%s code=%s status=%s)", order_id, exc.code, exc.status)
            raise CommerceError("estorno_falhou", "Não foi possível consultar o gateway agora. Tente novamente.", 502) from exc
        try:
            order = apply_refund_state(
                db, org_id, deps, order, paid_row, source=OrderEventSource.STAFF,
                newly_done=reconcile_refunds(db, org_id, order, paid_row, gw),
            )
            if order["status"] == OrderStatus.REFUNDED.value:
                await fire_revoked(deps, db, order, "refunded")
        except StaleOrder as exc:
            raise CommerceError("pedido_alterado", "O pedido mudou enquanto você agia. Recarregue.", 409) from exc
        except Exception:  # noqa: BLE001 - a finance hiccup must not block a refund; the next sync re-books (idempotent)
            logger.error("commerce refund: pre-sync of order=%s failed; continuing", order_id, exc_info=True)
            order = get_order(db, org_id, order_id)

    result = rpc_json(
        db.rpc(
            CREATE_REFUND_RPC,
            {
                "p_org_id": str(org_id),
                "p_order_id": str(order_id),
                "p_amount_cents": amount_cents,
                "p_reason": reason,
                "p_requested_by": str(requested_by) if requested_by else None,
                "p_idempotency_key": idempotency_key,
            },
        ).execute()
    )
    status = result.get("status")
    if status == "replayed":
        return result["refund"]
    if status != "created":
        raise _refusal(str(result.get("code")), {k: v for k, v in result.items() if k == "refundable_cents"})
    refund, charge = result["refund"], result["charge"]

    currency = order["currency"]
    try:
        gateway_refund = ops.refund_charge(
            charge["gateway_charge_id"], amount=Money(int(refund["amount_cents"]), currency), description=reason or "Reembolso",
        )
    except PaymentGatewayError as exc:
        _update(db, org_id, refund["id"], {"status": RefundStatus.FAILED.value}, only_status=RefundStatus.REQUESTED.value)
        logger.error("commerce refund: gateway refused order=%s refund=%s code=%s status=%s", order_id, refund["id"], exc.code, exc.status)
        if exc.code == "refund_exceeds_balance":
            raise CommerceError("valor_excede_saldo", "O gateway informa que o valor excede o saldo reembolsável.", 422) from exc
        if exc.code == "charge_not_refundable":
            raise CommerceError("pedido_nao_reembolsavel", "O gateway não permite reembolsar esta cobrança agora.", 409) from exc
        raise CommerceError("estorno_falhou", "O gateway recusou o reembolso. Nada foi estornado.", 502) from exc

    patch: dict[str, Any] = {"gateway_refund_id": gateway_refund.id_at_gateway} if gateway_refund.id_at_gateway else {}
    if gateway_refund.status == "done":
        patch.update({"status": RefundStatus.DONE.value, "done_at": now_iso()})
    saved = _update(db, org_id, refund["id"], patch) if patch else None
    refund = saved or {**refund, **patch}
    if refund["status"] == RefundStatus.DONE.value:
        paid_row = next(r for r in ensure_attempt_row(db, org_id, order) if str(r["id"]) == str(charge["id"]))
        try:
            after = apply_refund_state(db, org_id, deps, get_order(db, org_id, order_id), paid_row, source=OrderEventSource.STAFF, newly_done=[refund])
            if after["status"] == OrderStatus.REFUNDED.value:
                await fire_revoked(deps, db, after, "refunded")
        except StaleOrder:
            logger.warning("commerce refund: order=%s moved while recording the refund; the webhook will converge it", order_id)
        except Exception:  # noqa: BLE001 - the money moved: the refund row is the truth; the next sync converges the rest
            logger.error("commerce refund: refund=%s is done but the order/finance follow-up failed", refund["id"], exc_info=True)
    return refund


__all__ = [
    "MATCH_WINDOW",
    "STALE_REQUESTED_AFTER",
    "apply_refund_state",
    "create_refund",
    "list_refunds",
    "reconcile_refunds",
    "refunded_cents",
]
