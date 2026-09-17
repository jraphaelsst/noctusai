"""In-memory `TurnstileVerifier` — no IO, no Cloudflare account needed.

Mirrors `noctusai_lib.integrations.payments.fake.FakePaymentGateway`'s
posture: the executable example of the contract, plus a couple of test
seams (`accept` default, `rejected_tokens` overrides) so a consumer's own
test suite can drive both the pass and the 403 branch without ever
calling Cloudflare.
"""
from __future__ import annotations

from typing import Optional

from .types import TurnstileVerificationResult


class FakeTurnstileVerifier:
    """Deterministic in-memory `TurnstileVerifier`.

    Default posture: any non-empty token succeeds (`accept=True`), so a
    consumer's happy-path tests don't need to fabricate a real Cloudflare
    response. Two escape hatches for the failure branch:

    * ``accept=False`` at construction — every call fails (simulates a
      misconfigured/rotated secret).
    * ``rejected_tokens`` — a specific token value always fails, letting
      one test exercise both the 201-happy-path and the 403-invalid-token
      path with two different literal tokens against the SAME instance.
    """

    def __init__(self, *, accept: bool = True) -> None:
        self._accept = accept
        self.rejected_tokens: set[str] = set()
        # Recorded calls, so a test can assert on intent (which token/IP
        # was actually checked), not just the outcome.
        self.calls: list[tuple[str, Optional[str]]] = []

    async def verify(
        self, token: str, *, remote_ip: Optional[str] = None
    ) -> TurnstileVerificationResult:
        self.calls.append((token, remote_ip))
        if not token:
            return TurnstileVerificationResult(
                success=False, error_codes=("missing-input-response",)
            )
        if not self._accept or token in self.rejected_tokens:
            return TurnstileVerificationResult(
                success=False, error_codes=("invalid-input-response",)
            )
        return TurnstileVerificationResult(success=True)


__all__ = ["FakeTurnstileVerifier"]
