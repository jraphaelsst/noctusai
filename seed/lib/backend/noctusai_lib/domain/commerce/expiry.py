"""Void the gateway charge of an order that just expired (best effort, never silent).

The gateway keeps an OVERDUE boleto / Pix payable after our order expires. Left alive, a regenerate would put a
second live charge next to it and a late payment on the first would charge the buyer twice. So whenever an order
expires (the expire job, the overdue webhook) the charge is cancelled at the gateway right away; if that fails the
order stays expired, the failure is logged AND recorded as an order event, and `regenerate_payment` (which cancels
every non-paid attempt itself and refuses with 409 `cobranca_anterior_ativa` when it cannot) is the hard guarantee.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from .errors import CommerceError
from .gateway import CheckoutGateway
from .order_charges import cancel_gateway_charge, set_attempt_status
from .orders import append_event
from .types import ChargeAttemptStatus, OrderEventSource, OrderStatus

logger = logging.getLogger(__name__)

_VOIDABLE = (ChargeAttemptStatus.PENDING.value, ChargeAttemptStatus.EXPIRED.value)


def cancel_expired_charge(
    db: Any,
    org_id: Any,
    gateway: Optional[CheckoutGateway],
    order: Mapping[str, Any],
    row: Optional[Mapping[str, Any]],
    *,
    source: OrderEventSource,
) -> bool:
    """Cancel `row`'s charge at the gateway. True when it is dead (or there was nothing to cancel)."""
    if row is None or gateway is None or row["status"] not in _VOIDABLE:
        return True
    try:
        cancel_gateway_charge(gateway, org_id, row["gateway_charge_id"])
    except CommerceError as exc:
        logger.error("commerce: expired order=%s kept a live gateway charge (%s)", order["id"], exc.code)
        append_event(
            db, org_id, order["id"], from_status=OrderStatus.EXPIRED.value, to_status=OrderStatus.EXPIRED.value, source=source,
            reason=f"a cobrança da tentativa {row['attempt']} não pôde ser cancelada no gateway após o vencimento ({exc.code})",
        )
        return False
    set_attempt_status(db, org_id, row["id"], ChargeAttemptStatus.CANCELLED)
    return True


__all__ = ["cancel_expired_charge"]
