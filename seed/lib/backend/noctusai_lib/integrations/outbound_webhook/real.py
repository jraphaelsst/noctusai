"""The httpx-backed sender."""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from .types import DeliveryAttempt, DeliveryFailureKind, truncate_body

logger = logging.getLogger(__name__)

#: Ten seconds, matching what `products/core` has used in production.
#: A webhook subscriber that needs longer is not "slow", it is doing work
#: it should have queued — and our own caller is usually inside a request
#: or a background task with a budget of its own.
DEFAULT_TIMEOUT_SECONDS = 10.0

#: Sent on every delivery so a subscriber can identify us in their logs.
DEFAULT_USER_AGENT = "NoctusAI-Webhooks/1.0"


class HttpxOutboundWebhookSender:
    """Real `OutboundWebhookSender` over httpx.

    `http_client` is injectable for tests that want to assert on the
    request without a network stack. When it is `None` a client is built
    per call — deliveries are infrequent and usually already inside a
    background task, so a shared pooled client would buy little and would
    make the sender stateful across event loops.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        http_client: Any = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._user_agent = user_agent
        self._http_client = http_client

    def _headers(self, headers: Optional[Mapping[str, str]]) -> dict[str, str]:
        # Caller-supplied headers win: a consumer forwarding a vendor's
        # request verbatim must be able to override even Content-Type.
        merged = {
            "Content-Type": "application/json",
            "User-Agent": self._user_agent,
        }
        merged.update(dict(headers or {}))
        return merged

    async def send(
        self,
        *,
        url: str,
        body: str,
        headers: Optional[Mapping[str, str]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> DeliveryAttempt:
        # Imported here rather than at module scope so that importing the
        # package does not require httpx in an environment that only ever
        # touches the Fake (tests, CLI tooling).
        import httpx

        timeout = timeout_seconds if timeout_seconds is not None else self._timeout
        request_headers = self._headers(headers)

        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    url, content=body, headers=request_headers, timeout=timeout
                )
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        url, content=body, headers=request_headers
                    )
        except httpx.TimeoutException as exc:
            # Not an error log: a timeout is an expected outcome the
            # caller is about to record and retry. Logging it at ERROR
            # trains operators to ignore the level that matters.
            logger.warning("outbound-webhook: timeout url=%s", url)
            return DeliveryAttempt(
                succeeded=False,
                failure_kind=DeliveryFailureKind.TIMEOUT,
                error=str(exc)[:200] or "timeout",
            )
        except httpx.RequestError as exc:
            logger.warning("outbound-webhook: transport error url=%s err=%s", url, exc)
            return DeliveryAttempt(
                succeeded=False,
                failure_kind=DeliveryFailureKind.TRANSPORT_ERROR,
                error=str(exc)[:200],
            )

        status = response.status_code
        text = truncate_body(getattr(response, "text", None))

        if 200 <= status < 300:
            return DeliveryAttempt(
                succeeded=True, status_code=status, response_body=text
            )

        return DeliveryAttempt(
            succeeded=False,
            status_code=status,
            response_body=text,
            failure_kind=DeliveryFailureKind.HTTP_ERROR,
        )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_USER_AGENT",
    "HttpxOutboundWebhookSender",
]
