"""The single seam consumers reach for — Fake or the Real verifier."""
from __future__ import annotations

from typing import Optional

import httpx

from .fake import FakeTurnstileVerifier
from .protocol import TurnstileVerifier
from .real import DEFAULT_TIMEOUT_SECONDS, DEFAULT_VERIFY_URL, RealTurnstileVerifier


def make_turnstile_verifier(
    *,
    use_fake: bool = False,
    secret: Optional[str] = None,
    verify_url: str = DEFAULT_VERIFY_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    transport: Optional[httpx.BaseTransport] = None,
) -> TurnstileVerifier:
    """Build a `TurnstileVerifier`.

    Args:
        use_fake: when True, always return `FakeTurnstileVerifier` — the
            dev/test path. Tests should prefer constructing
            `FakeTurnstileVerifier` directly (DI seam) over this flag;
            it exists for parity with `make_payment_gateway`'s shape.
        secret: the Turnstile secret key (`COMMUNITY_TURNSTILE_SECRET` or
            equivalent per-consumer setting). `None`/empty ALSO returns
            the Fake — same early-dev-bypass posture the platform already
            uses for webhook secrets (`bypass_when_unset`), so a product
            boots cleanly before Cloudflare keys are configured. Unlike a
            signature-bypass, this only ever affects a Fake instance that
            still rejects an EMPTY token — a missing `turnstile_token`
            still 403s even with no secret configured.
        verify_url / timeout_seconds / transport: Real-adapter tuning;
            `transport` is the test seam (`httpx.MockTransport`).

    Returns:
        `FakeTurnstileVerifier` when `use_fake` or `secret` is falsy,
        else `RealTurnstileVerifier(secret=secret, ...)`.
    """
    if use_fake or not secret:
        return FakeTurnstileVerifier()
    return RealTurnstileVerifier(
        secret=secret,
        verify_url=verify_url,
        timeout_seconds=timeout_seconds,
        transport=transport,
    )


__all__ = ["make_turnstile_verifier"]
