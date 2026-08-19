"""In-memory sender for tests and dev.

Records every request and returns scripted outcomes. It exists so a
consumer can prove its *retry and persistence* behaviour — which is where
the real bugs live — without a network, a subscriber, or a sleep.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from .types import DeliveryAttempt, DeliveryFailureKind


@dataclass(frozen=True)
class RecordedRequest:
    """One captured delivery, for assertions."""

    url: str
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: Optional[float] = None


class FakeOutboundWebhookSender:
    """Scriptable `OutboundWebhookSender`.

    Args:
        outcomes: consumed in order, one per `send`. When exhausted (or
            not supplied) `default_outcome` is returned for every further
            call. A finite script followed by an infinite default is what
            lets a test say "fail twice, then succeed" without also
            asserting how many times the consumer retries.
        default_outcome: returned once `outcomes` runs out. Defaults to
            success.
    """

    def __init__(
        self,
        *,
        outcomes: Optional[list[DeliveryAttempt]] = None,
        default_outcome: Optional[DeliveryAttempt] = None,
    ) -> None:
        self._outcomes = list(outcomes or [])
        self._default = default_outcome or DeliveryAttempt(
            succeeded=True, status_code=200, response_body="ok"
        )
        self.requests: list[RecordedRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    @property
    def last_request(self) -> Optional[RecordedRequest]:
        return self.requests[-1] if self.requests else None

    async def send(
        self,
        *,
        url: str,
        body: str,
        headers: Optional[Mapping[str, str]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> DeliveryAttempt:
        self.requests.append(
            RecordedRequest(
                url=url,
                body=body,
                headers=dict(headers or {}),
                timeout_seconds=timeout_seconds,
            )
        )
        if self._outcomes:
            return self._outcomes.pop(0)
        return self._default


def failure(
    *,
    status_code: Optional[int] = None,
    kind: DeliveryFailureKind = DeliveryFailureKind.HTTP_ERROR,
    body: Optional[str] = None,
) -> DeliveryAttempt:
    """Shorthand for scripting a failed attempt in a test."""
    return DeliveryAttempt(
        succeeded=False,
        status_code=status_code,
        response_body=body,
        failure_kind=kind,
    )


def success(status_code: int = 200, body: Optional[str] = "ok") -> DeliveryAttempt:
    """Shorthand for scripting a successful attempt in a test."""
    return DeliveryAttempt(
        succeeded=True, status_code=status_code, response_body=body
    )


__all__ = [
    "FakeOutboundWebhookSender",
    "RecordedRequest",
    "failure",
    "success",
]
