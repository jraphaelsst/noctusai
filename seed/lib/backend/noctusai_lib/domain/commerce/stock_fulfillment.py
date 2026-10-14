"""`StockFulfillment` -- the commerce fulfillment handler that holds, ships and gives back STOCK (roadmap E6).

Registered (by the host) for the physical fulfillment types, it drives the inventory organ's `StockPort`:

    order about to be created  -> `reserve`   (all or none; refuses the sale with 409 `estoque_insuficiente`)
    paid                       -> `commit`    (the reservation becomes a stock-out at the average cost)
    expired / cancelled        -> `release`   (the hold is given back)
    revoked (refund/chargeback)-> `release`   (a COMMITTED line has already left: logged, see NOC-REMEDIATE below)

Only order lines whose PRODUCT carries an `item_id` (`commerce_products.item_id`, ERP link delta) take part -- a digital
product, or a physical one the merchant does not track, needs no stock. Every call is idempotent on the order ref (the
order id), so a re-delivered webhook or a re-run sweep never holds or ships twice.

Money is real: when a PAID order's hold was lost (it expired and the buyer paid late, or the product was linked after the
order) the handler re-holds under `<order>:late` and commits; if even that is refused the sale stands and the shortage is
logged at ERROR for staff -- the handler never raises over a confirmed payment.

NOC-REMEDIATE[commerce-stock-short-alert]: a shortage found at payment time is only logged; a staff e-mail (async
`notify_staff`) needs an async fulfillment hook. -- 2026-10-14
NOC-REMEDIATE[commerce-return-to-stock]: a refund/chargeback after commit does not put the goods back; that is a
returns flow (inventory `receive`/`adjust`), not an automatic reversal. -- 2026-10-14
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional, Sequence

from noctusai_lib.domain.inventory.errors import (
    ESTOQUE_INSUFICIENTE,
    RESERVA_CONSUMIDA,
    RESERVA_LIBERADA,
    SEM_RESERVA,
    InventoryError,
)
from noctusai_lib.domain.inventory.port import StockPort
from noctusai_lib.integrations.persistence.table_reads import in_batched_rows

from .errors import CommerceError
from .fulfillment import NoopFulfillment

logger = logging.getLogger(__name__)

#: A hold that has to be (re)acquired when the money arrives lives under this suffix of the order ref (a released
#: reservation can never be re-reserved under the same ref -- the inventory RPC is idempotent on it).
LATE_REF_SUFFIX = ":late"

ESTOQUE_INSUFICIENTE_MESSAGE = "Estoque insuficiente para um ou mais itens do pedido."


def order_ref(order: Mapping[str, Any]) -> str:
    """The stock reference of an order: its id."""
    return str(order["id"])


class StockFulfillment(NoopFulfillment):
    """See the module docstring. `get_stock()` / `get_db()` are called per use (never captured at import)."""

    def __init__(
        self,
        *,
        get_stock: Callable[[], StockPort],
        get_db: Callable[[], Any],
        products_table: str = "commerce_products",
    ) -> None:
        self._get_stock = get_stock
        self._get_db = get_db
        self._products = products_table

    # -- which lines take part ---------------------------------------------------------------------------------
    def stock_lines(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[dict]:
        """`[{item_id, qty}]` for the order lines whose product is linked to an item (qty summed per item)."""
        product_ids = [str(i["product_id"]) for i in items if i.get("product_id")]
        if not product_ids:
            return []
        rows = in_batched_rows(self._get_db(), self._products, order["org_id"], "id", product_ids, select="id,item_id")
        item_of = {str(r["id"]): str(r["item_id"]) for r in rows if r.get("item_id")}
        wanted: dict[str, int] = {}
        for line in items:
            item_id = item_of.get(str(line.get("product_id") or ""))
            if item_id:
                wanted[item_id] = wanted.get(item_id, 0) + int(line["qty"])
        return [{"item_id": item_id, "qty": qty} for item_id, qty in sorted(wanted.items())]

    # -- lifecycle ---------------------------------------------------------------------------------------------
    def on_created(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        lines = self.stock_lines(order, items)
        if not lines:
            return
        try:
            self._get_stock().reserve(str(order["org_id"]), order_ref(order), lines)
        except InventoryError as exc:
            if exc.code == ESTOQUE_INSUFICIENTE:
                raise CommerceError(ESTOQUE_INSUFICIENTE, ESTOQUE_INSUFICIENTE_MESSAGE, 409, details=exc.details) from exc
            raise CommerceError(exc.code, exc.message, exc.status_code, details=exc.details) from exc

    def on_paid(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        lines = self.stock_lines(order, items)
        if not lines:
            return
        org, ref, stock = str(order["org_id"]), order_ref(order), self._get_stock()
        keys = [{"item_id": ln["item_id"]} for ln in lines]
        try:
            stock.commit(org, ref, keys)
            return
        except InventoryError as exc:
            if exc.code not in (RESERVA_LIBERADA, SEM_RESERVA):
                raise
            logger.warning("commerce stock: order=%s paid without a live hold (%s); re-holding at payment", ref, exc.code)
        late = ref + LATE_REF_SUFFIX
        try:
            stock.reserve(org, late, lines)
            stock.commit(org, late, keys)
        except InventoryError as exc:
            # The money is real: the sale stands, the shortage is for a human (see NOC-REMEDIATE[commerce-stock-short-alert]).
            logger.error(
                "commerce stock: order=%s is PAID but its stock could not be committed (%s); needs manual handling",
                ref, exc.code,
            )

    def _release(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]], *, why: str) -> None:
        lines = self.stock_lines(order, items)
        if not lines:
            return
        keys = [{"item_id": ln["item_id"]} for ln in lines]
        try:
            self._get_stock().release(str(order["org_id"]), order_ref(order), keys)
        except InventoryError as exc:
            if exc.code != RESERVA_CONSUMIDA:
                raise
            logger.info("commerce stock: order=%s already left stock (%s); not restocked automatically", order_ref(order), why)

    def on_expired(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        self._release(order, items, why="expired")

    def on_cancelled(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        self._release(order, items, why="cancelled")

    def on_revoked(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        self._release(order, items, why="revoked")


__all__ = ["ESTOQUE_INSUFICIENTE_MESSAGE", "LATE_REF_SUFFIX", "StockFulfillment", "order_ref"]
