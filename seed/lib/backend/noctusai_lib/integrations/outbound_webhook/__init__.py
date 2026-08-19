"""Outbound webhook delivery — one attempt, reported as data.

**What this is.** The part every outbound-delivery path otherwise
rewrites: issue a POST, and turn the result — including a timeout, a
refused connection or a 500 — into a `DeliveryAttempt` the caller can
persist, compare and decide to retry. It never raises for a failed
delivery, because both known consumers must record that failure durably
and an escaping exception is how a payload gets lost between "received"
and "logged".

**What it is deliberately NOT.** Not a retry loop: the seed already ships
exponential-backoff math at `noctusai_lib.domain.jobs.retry_policy`
(`RetryPolicy` / `next_retry_at`), already consumed by
`social-wiring`'s scheduling module, and a second backoff implementation
in the same library is the fork this package exists to avoid. Not a
persistence layer: which table a delivery is logged to, and what of the
payload may legally be stored, are product decisions. Not an auth
scheme: callers pass finished headers.

**Consumers.**

* `products/core` — signs an HMAC envelope, logs to `webhook_deliveries`,
  minimises the stored payload for LGPD.
* `products/social-wiring` — forwards Grupo OLX portal leads to a
  downstream CRM, passing the vendor's own `Authorization` header
  through untouched and keeping the body verbatim, because the body IS
  the thing being delivered.

Two consumers, two different auth schemes, two different retention
rules, one delivery attempt.

**Recipe:**

    from noctusai_lib.integrations.outbound_webhook import (
        make_outbound_webhook_sender,
    )
    from noctusai_lib.domain.jobs.retry_policy import RetryPolicy, next_retry_at

    sender = make_outbound_webhook_sender()
    attempt = await sender.send(url=url, body=body, headers=headers)
    if attempt.succeeded:
        ...
    elif attempt.is_retryable:
        schedule_at = next_retry_at(retries_so_far, policy, now)
    else:
        ...  # a 4xx: the subscriber understood and refused; do not spend retries
"""
from __future__ import annotations

from .factory import make_outbound_webhook_sender
from .fake import FakeOutboundWebhookSender, RecordedRequest, failure, success
from .protocol import OutboundWebhookSender
from .real import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    HttpxOutboundWebhookSender,
)
from .types import (
    RESPONSE_BODY_LIMIT,
    DeliveryAttempt,
    DeliveryFailureKind,
    truncate_body,
)

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_USER_AGENT",
    "RESPONSE_BODY_LIMIT",
    "DeliveryAttempt",
    "DeliveryFailureKind",
    "FakeOutboundWebhookSender",
    "HttpxOutboundWebhookSender",
    "OutboundWebhookSender",
    "RecordedRequest",
    "failure",
    "make_outbound_webhook_sender",
    "success",
    "truncate_body",
]
