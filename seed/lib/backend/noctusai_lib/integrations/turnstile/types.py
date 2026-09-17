"""Value objects for Cloudflare Turnstile verification.

Pure: no IO. `TurnstileVerificationResult` is the one shape both the Fake
and the Real adapter return, so a consumer never branches on which one it
is talking to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TurnstileVerificationResult:
    """Outcome of one `siteverify` call (or its Fake equivalent).

    `success=False` covers every failure mode a consumer needs to treat
    identically (missing token, wrong secret, expired/already-consumed
    token, Cloudflare unreachable) — the caller's job is "was this human,
    yes or no", not diagnosing which of Cloudflare's ~10 `error-codes`
    fired. `error_codes` and `raw` are forensic, for logs only.
    """

    success: bool
    error_codes: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


__all__ = ["TurnstileVerificationResult"]
