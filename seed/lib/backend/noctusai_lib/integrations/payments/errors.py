"""One error type for both gateways.

Deliberately not `HTTPException` — mirrors `products/p-studio`'s
`ErroProvedor` rationale exactly: a gateway call can happen inside a
webhook handler or a background job, not only inside an HTTP request,
and raising an HTTP-flavored exception there is the wrong shape. A
consumer's router translates `PaymentGatewayError` to HTTP; a webhook
handler or job worker catches it and decides retry/no-retry from
`retryable`.

Both Real adapters raise this SAME class (never a Stripe-specific or
Asaas-specific subclass) — that symmetry is what lets a consumer catch
one exception type regardless of which gateway is configured, matching
the Protocol's own gateway-agnostic contract.
"""
from __future__ import annotations

from typing import Optional


class PaymentGatewayError(Exception):
    """A call to a payment gateway failed."""

    def __init__(
        self,
        gateway: str,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        retryable: bool = False,
    ) -> None:
        self.gateway = gateway
        self.message = message
        self.status = status
        self.code = code
        # Timeouts and 5xx are worth retrying; a 4xx means the payload
        # or the request itself was wrong and retrying identically will
        # fail identically while burning the retry budget.
        self.retryable = retryable
        super().__init__(f"[{gateway}] {message}")

    def __repr__(self) -> str:  # pragma: no cover - diagnostic
        return (
            f"PaymentGatewayError(gateway={self.gateway!r}, status={self.status!r}, "
            f"code={self.code!r}, retryable={self.retryable!r}, message={self.message!r})"
        )


__all__ = ["PaymentGatewayError"]
