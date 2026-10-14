"""`CommerceQuoteAcceptHandler` -- the `QuoteAcceptHandler` that turns an accepted GOODS quote into a commerce ORDER.

Roadmap E7: a staff/quote-made sales order IS a commerce order, on the `manual` channel -- not a second sales-order model.
The order is created in `created` (a draft: no gateway charge, no tender yet), carries the quote's id as `source_ref`
(`UNIQUE (org_id, source_ref)`, ERP link delta `erp_sql`) and is IDEMPOTENT on it: a retried conversion returns the SAME order.

What it does, in order:

1. found by `source_ref` -> return it (idempotent);
2. the quote's party becomes the commerce customer (`upsert_buyer`, source `staff`; a party WITHOUT an e-mail cannot be
   an order's customer -> 422 `cliente_sem_email`, the conversion is marked `failed` and retried after the fix);
3. each quote line becomes an order line; a line whose `item_id` is the item of a catalog product links to that product (so
   its fulfillment type and stock behaviour follow the product), any other goods line is a plain `none` line;
4. the fulfillment registry's `on_created` runs BEFORE the order row is written: stock is held (E6), and an oversell refuses
   the whole conversion with 409 `estoque_insuficiente` -- nothing is written;
5. order + lines + the `created` event are written; a failure after the hold gives the hold back.

Order lines are positive integers (`qty > 0`, `total_cents > 0`): a fractional quantity or a free line cannot be an order line
and fails the conversion with a clear pt-BR error -- quote it as a service (contract) or fix the line.

NOC-REMEDIATE[commerce-manual-order-charge]: the order waits in `created`; opening a gateway charge for a manual order (a
payment link staff send) is the next slice. Until then staff cancel it (stock is released) or register the sale elsewhere. -- 2026-10-14
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Mapping, Optional, Sequence

from noctusai_lib.domain.quotes.handler import QuoteAcceptContext, QuoteConversion
from noctusai_lib.integrations.persistence.table_reads import in_batched_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import first, new_id, now_iso, tbl
from .customers import upsert_buyer
from .errors import CommerceError
from .fulfillment import FulfillmentRegistry
from .orders import append_event, new_token
from .types import FieldSource, OrderChannel, OrderEventSource, OrderStatus

logger = logging.getLogger(__name__)

_ORDERS = "commerce_orders"
_ITEMS = "commerce_order_items"
_PRODUCTS = "commerce_products"

CLIENTE_SEM_EMAIL = "cliente_sem_email"
LINHA_INVALIDA_PARA_PEDIDO = "linha_invalida_para_pedido"


def _int_qty(line: Mapping[str, Any], index: int) -> int:
    qty = Decimal(str(line["qty"]))
    if qty != qty.to_integral_value() or qty < 1:
        raise CommerceError(
            LINHA_INVALIDA_PARA_PEDIDO,
            f"A linha {index + 1} tem quantidade fracionada ({qty.normalize():f}); um pedido só aceita unidades inteiras.",
            422,
            details={"line": index + 1},
        )
    return int(qty)


class CommerceQuoteAcceptHandler:
    """See the module docstring. `get_db()` / `get_fulfillment()` are called per conversion (never captured at import)."""

    def __init__(
        self,
        *,
        get_db: Callable[[], Any],
        get_fulfillment: Optional[Callable[[], FulfillmentRegistry]] = None,
        parties_table: str = "pty_parties",
        currency: str = "BRL",
    ) -> None:
        self._get_db = get_db
        self._get_fulfillment = get_fulfillment
        self._parties = parties_table
        self._currency = currency

    # -- pieces ------------------------------------------------------------------------------------------------
    def _existing(self, db: Any, org_id: str, quote_id: str) -> Optional[dict]:
        return first(tbl(db, _ORDERS).select("*").eq("org_id", org_id).eq("source_ref", quote_id).limit(1).execute())

    def _customer(self, db: Any, org_id: str, party_id: str) -> dict:
        party = first(tbl(db, self._parties).select("*").eq("org_id", org_id).eq("id", party_id).limit(1).execute())
        if party is None:
            raise CommerceError("cliente_nao_encontrado", "O cliente do orçamento não foi encontrado.", 422)
        email = (party.get("email") or "").strip()
        if not email:
            raise CommerceError(CLIENTE_SEM_EMAIL, "O cliente do orçamento não tem e-mail; cadastre-o e converta novamente.", 422)
        phones = party.get("phones") or []
        phone = next((p if isinstance(p, str) else str((p or {}).get("number") or "") for p in phones), None)
        return upsert_buyer(
            db, org_id,
            {
                "name": party.get("trade_name") or party["legal_name"], "email": email, "doc": party.get("doc"),
                "phone": phone, "address": party.get("address") or {},
            },
            source=FieldSource.STAFF,
        )

    def _products_by_item(self, db: Any, org_id: str, item_ids: Sequence[str]) -> dict[str, dict]:
        rows = in_batched_rows(db, _PRODUCTS, org_id, "item_id", list(item_ids), select="id,item_id,product_type,fulfillment_type,created_at")
        out: dict[str, dict] = {}
        for row in sorted(rows, key=lambda r: (str(r.get("created_at") or ""), str(r["id"]))):
            out.setdefault(str(row["item_id"]), row)  # several products on one item: the oldest wins, deterministically
        return out

    def _item_rows(self, db: Any, org_id: str, order_id: str, lines: Sequence[Mapping[str, Any]]) -> list[dict]:
        wanted = sorted({str(ln["item_id"]) for ln in lines if ln.get("item_id")})
        product_of = self._products_by_item(db, org_id, wanted) if wanted else {}
        rows: list[dict] = []
        for i, line in enumerate(lines):
            qty = _int_qty(line, i)
            total = int(line["total_cents"])
            if total <= 0:
                raise CommerceError(
                    LINHA_INVALIDA_PARA_PEDIDO, f"A linha {i + 1} não tem valor; um pedido não aceita linhas gratuitas.", 422, details={"line": i + 1},
                )
            product = product_of.get(str(line.get("item_id") or ""))
            unit = max(1, int((Decimal(total) / qty).quantize(Decimal(1), rounding=ROUND_HALF_UP)))
            rows.append({
                "id": new_id(), "org_id": org_id, "order_id": order_id,
                "product_id": str(product["id"]) if product else None,
                "offer_id": None,
                "title_snapshot": str(line["description"])[:300],
                "product_type": product["product_type"] if product else "physical",
                "fulfillment_type": product["fulfillment_type"] if product else "none",
                "unit_price_cents": unit, "qty": qty, "total_cents": total,
            })
        return rows

    # -- the seam ----------------------------------------------------------------------------------------------
    def handle(self, ctx: QuoteAcceptContext) -> Optional[QuoteConversion]:
        db, org_id = self._get_db(), str(ctx.org_id)
        quote = ctx.quote
        quote_id = str(quote["id"])
        found = self._existing(db, org_id, quote_id)
        if found is not None:
            return QuoteConversion(kind="order", ref=str(found["id"]), detail={"created": False})
        if not ctx.lines:
            raise CommerceError(LINHA_INVALIDA_PARA_PEDIDO, "O orçamento não tem linhas.", 422)

        customer = self._customer(db, org_id, str(quote["party_id"]))
        order_id = new_id()
        items = self._item_rows(db, org_id, order_id, ctx.lines)
        fulfillment = self._get_fulfillment() if self._get_fulfillment else None
        held = False
        try:
            if fulfillment is not None:
                held = True  # before the call: a hook that refused halfway may already hold some lines
                fulfillment.dispatch_created({"id": order_id, "org_id": org_id}, items)
            at = now_iso()
            order_row = {
                "id": order_id, "org_id": org_id, "token": new_token(), "customer_id": str(customer["id"]),
                "status": OrderStatus.CREATED.value,
                "subtotal_cents": int(quote["subtotal_cents"]), "discount_cents": int(quote["discount_cents"]),
                "total_cents": int(quote["total_cents"]), "currency": quote.get("currency") or self._currency,
                "payment_method": None, "gateway": None, "channel": OrderChannel.MANUAL.value, "source_ref": quote_id,
                "platform_fee_cents": 0, "created_at": at, "updated_at": at,
            }
            try:
                tbl(db, _ORDERS).insert(order_row).execute()
            except Exception as exc:  # noqa: BLE001 - narrowed below
                if not is_unique_violation(exc):
                    raise
                # A concurrent conversion of the same quote won: its order is THE order; give our hold back.
                winner = self._existing(db, org_id, quote_id)
                if winner is None:
                    raise
                self._give_back(fulfillment if held else None, order_id, org_id, items)
                return QuoteConversion(kind="order", ref=str(winner["id"]), detail={"created": False})
            try:
                tbl(db, _ITEMS).insert(items).execute()
            except Exception:
                tbl(db, _ORDERS).delete().eq("org_id", org_id).eq("id", order_id).execute()  # no half-written order
                raise
            append_event(
                db, org_id, order_id, from_status=None, to_status=OrderStatus.CREATED.value, source=OrderEventSource.SYSTEM,
                reason=f"pedido criado a partir do orçamento {quote.get('number') or quote_id}",
            )
        except Exception:
            self._give_back(fulfillment if held else None, order_id, org_id, items)
            raise
        return QuoteConversion(kind="order", ref=order_id, detail={"created": True})

    @staticmethod
    def _give_back(fulfillment: Optional[FulfillmentRegistry], order_id: str, org_id: str, items: list[dict]) -> None:
        if fulfillment is None:
            return
        try:
            fulfillment.dispatch_cancelled({"id": order_id, "org_id": org_id}, items)
        except Exception:  # noqa: BLE001 - logged; the caller is already handling the real failure
            logger.error("commerce quote conversion: could not release the stock hold of order=%s", order_id, exc_info=True)


__all__ = ["CLIENTE_SEM_EMAIL", "CommerceQuoteAcceptHandler", "LINHA_INVALIDA_PARA_PEDIDO"]
