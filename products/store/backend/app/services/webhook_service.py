"""Asaas webhook handling — claim -> dispatch -> release-on-failure.

The router has ALREADY verified the delivery (`parse_webhook_event`: bad or
unset token => 401 before anything below runs) and hands over a verified,
normalized `GatewayEvent`.

* Duplicates: the seed `EventInbox` claim (PK `(gateway, event_id)`). A
  claimed-then-crashed delivery is released so Asaas' retry is not lost.
* `charge_paid` -> pedido `pago` + the delivery email exactly once (the
  email has its own atomic claim, so PAYMENT_CONFIRMED + PAYMENT_RECEIVED —
  two distinct event ids — still send one email).
* `charge_refunded` -> `reembolsado` (downloads stop at once).
* `charge_failed` (overdue) -> `falhou`, only for a still-`pendente` pedido.
* Anything else / an unknown pedido -> ignored, 200 (webhooks retry forever
  on a non-2xx; an event we do not act on is never an error).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from noctusai_lib.domain.payments import EventInbox
from noctusai_lib.integrations.payments.webhook_events import GatewayEvent

from app.services.delivery_service import DeliveryFailed, DeliveryService
from app.stores.protocols import PedidoStore

logger = logging.getLogger(__name__)


class WebhookService:
    def __init__(
        self,
        *,
        pedidos: PedidoStore,
        inbox: EventInbox,
        delivery: DeliveryService,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._pedidos = pedidos
        self._inbox = inbox
        self._delivery = delivery
        self._now = now_fn

    def _find_pedido(self, event: GatewayEvent) -> Optional[dict[str, Any]]:
        if event.external_reference:
            found = self._pedidos.get_by_id(event.external_reference)
            if found is not None:
                return found
        if event.charge_id_at_gateway:
            return self._pedidos.get_by_charge_id(event.charge_id_at_gateway)
        return None

    async def handle(self, event: GatewayEvent) -> str:
        """Returns `duplicate` | `ignored` | `processed`."""
        gateway, event_id = event.inbox_key
        if not self._inbox.claim(gateway=gateway, event_id=event_id):
            return "duplicate"
        try:
            return await self._dispatch(event)
        except Exception:
            self._inbox.release(gateway=gateway, event_id=event_id)
            raise

    async def _dispatch(self, event: GatewayEvent) -> str:
        if event.kind not in ("charge_paid", "charge_refunded", "charge_failed"):
            return "ignored"
        pedido = self._find_pedido(event)
        if pedido is None:
            logger.warning("webhook: %s for an unknown pedido (event ignored)", event.kind)
            return "ignored"
        pedido_id = str(pedido["id"])

        if event.kind == "charge_paid":
            if pedido["status"] == "reembolsado":
                # A late/out-of-order paid event must never resurrect a refunded order.
                logger.warning("webhook: charge_paid for an already-refunded pedido=%s ignored", pedido_id)
                return "ignored"
            fields: dict[str, Any] = {"status": "pago"}
            if pedido["status"] != "pago":
                fields["pago_em"] = self._now().isoformat()
            if event.charge_id_at_gateway and not pedido.get("gateway_charge_id"):
                fields["gateway_charge_id"] = event.charge_id_at_gateway
            updated = self._pedidos.update(pedido_id, fields) or {**pedido, **fields}
            try:
                await self._delivery.send_once(updated)
            except DeliveryFailed:
                # Already recorded on the pedido + logged at error level by the
                # delivery service. The payment is confirmed; answering non-2xx
                # would only make Asaas retry (and eventually pause the queue).
                # The owner re-sends from /admin/vendas.
                logger.error("webhook: pedido=%s paid but the delivery email failed (recorded)", pedido_id)
            return "processed"

        if event.kind == "charge_refunded":
            self._pedidos.update(pedido_id, {"status": "reembolsado"})
            return "processed"

        # charge_failed
        if pedido["status"] == "pendente":
            self._pedidos.update(pedido_id, {"status": "falhou"})
        return "processed"


__all__ = ["WebhookService"]
