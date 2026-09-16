"""Webhook authentication across modes, over the seed parser.

Verification and normalization are the seed's
(`noctusai_lib.integrations.payments.webhook_events.parse_webhook_event`).
What Core adds: both gateways may have a TEST and a LIVE webhook registered
at once, so a delivery is tried against the secret of every configured mode
and the mode that verified it travels with the event — that mode picks the
API key used to act on it. Checking only the active mode would reject the
other environment's deliveries, and repeated rejections make Asaas pause
the whole delivery queue.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from noctusai_lib.integrations.payments.webhook_events import (
    GatewayEvent,
    PaymentWebhookSignatureError,
    parse_webhook_event,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedGatewayEvent:
    gateway: str  # "stripe" | "asaas"
    mode: str  # "test" | "live"
    event_id: str
    event_type: str  # the gateway's raw event name
    payload: dict[str, Any]
    event: GatewayEvent

    @property
    def inbox_key(self) -> tuple[str, str]:
        return self.event.inbox_key


class WebhookNotConfigured(RuntimeError):
    """No secret is configured for any mode — our gap, not the caller's."""


class WebhookAuthError(RuntimeError):
    """The delivery did not verify against any configured secret."""


def parse_for_any_mode(
    gateway: str, body: bytes, headers: Mapping[str, str], secrets_by_mode: dict[str, str]
) -> ParsedGatewayEvent:
    if not secrets_by_mode:
        raise WebhookNotConfigured(f"Nenhum segredo de webhook {gateway} configurado.")
    last_error: PaymentWebhookSignatureError | None = None
    for mode, secret in secrets_by_mode.items():
        kwargs = (
            {"stripe_webhook_secret": secret} if gateway == "stripe" else {"asaas_webhook_token": secret}
        )
        try:
            event = parse_webhook_event(body, headers, gateway=gateway, **kwargs)
        except PaymentWebhookSignatureError as exc:
            last_error = exc
            continue
        raw = event.raw or {}
        if gateway == "stripe":
            livemode = raw.get("livemode")
            if livemode is not None and (mode == "live") != bool(livemode):
                # Verified by this mode's secret but flagged for the other
                # mode: the same secret was pasted into both slots. Refuse.
                raise WebhookAuthError("Evento Stripe com livemode diferente do segredo que o assinou.")
            event_type = str(raw.get("type") or "")
        else:
            event_type = str(raw.get("event") or "")
        return ParsedGatewayEvent(gateway, mode, event.event_id, event_type, raw, event)
    logger.warning("billing_events: %s delivery verified against no configured mode (%s)", gateway, last_error)
    raise WebhookAuthError(last_error.detail if last_error else "assinatura inválida")


__all__ = ["ParsedGatewayEvent", "WebhookAuthError", "WebhookNotConfigured", "parse_for_any_mode"]
