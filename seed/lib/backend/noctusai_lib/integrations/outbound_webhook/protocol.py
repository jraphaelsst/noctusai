"""The sender Protocol both halves implement."""
from __future__ import annotations

from typing import Mapping, Optional, Protocol

from .types import DeliveryAttempt


class OutboundWebhookSender(Protocol):
    """POST one body to one URL and report what happened.

    Deliberately narrow. It does **not** own:

    * **retry** — scheduling belongs to the consumer, using the seed's
      existing `noctusai_lib.domain.jobs.retry_policy` (`RetryPolicy` /
      `next_retry_at`). A retry loop here would be a second backoff
      implementation in the same library as that one;
    * **persistence** — which table a delivery is logged to, and what of
      the payload may be stored, are product decisions (core minimises
      payloads for LGPD; a lead forwarder keeps the body because the body
      IS the thing being delivered);
    * **authentication** — callers pass finished `headers`. Signing an
      HMAC envelope and passing a vendor's `Authorization` header
      through untouched are both just headers, and inventing an auth
      abstraction to cover two cases that simple would obscure both.

    What it does own is the part every caller otherwise rewrites: issuing
    the request, and turning "it didn't work" into a durable, comparable
    outcome instead of an exception.
    """

    async def send(
        self,
        *,
        url: str,
        body: str,
        headers: Optional[Mapping[str, str]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> DeliveryAttempt:
        """Issue one POST. MUST NOT raise for a failed delivery.

        A transport error, a timeout and a 500 are all ordinary results
        here, returned as a `DeliveryAttempt` with `succeeded=False`. The
        contract exists because both known consumers must record the
        failure durably; an exception escaping this call is how a payload
        gets lost between "received" and "logged".
        """
        ...


__all__ = ["OutboundWebhookSender"]
