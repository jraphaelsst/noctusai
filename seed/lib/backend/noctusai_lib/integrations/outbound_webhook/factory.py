"""The single seam consumers reach for — Fake or Real, by flag."""
from __future__ import annotations

from typing import Any, Optional, Union

from .fake import FakeOutboundWebhookSender
from .real import DEFAULT_TIMEOUT_SECONDS, DEFAULT_USER_AGENT, HttpxOutboundWebhookSender


def make_outbound_webhook_sender(
    *,
    use_fake: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
    http_client: Any = None,
    fake_outcomes: Optional[list] = None,
    fake_default_outcome: Optional[Any] = None,
) -> Union[HttpxOutboundWebhookSender, FakeOutboundWebhookSender]:
    """Build a sender. Both branches satisfy `OutboundWebhookSender`, so a
    consumer selects here once and never branches on environment itself.

    Unlike the credentialled seed clients, there is nothing to be
    unconfigured about: a sender with no destination is simply never
    called. The destination and its headers arrive per-delivery.
    """
    if use_fake:
        return FakeOutboundWebhookSender(
            outcomes=fake_outcomes, default_outcome=fake_default_outcome
        )
    return HttpxOutboundWebhookSender(
        timeout_seconds=timeout_seconds,
        user_agent=user_agent,
        http_client=http_client,
    )


__all__ = ["make_outbound_webhook_sender"]
