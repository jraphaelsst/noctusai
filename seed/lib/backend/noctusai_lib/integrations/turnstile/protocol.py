"""`TurnstileVerifier` — the Protocol every adapter (Fake + Real) satisfies.

One verb: given the token a Cloudflare Turnstile widget handed the
frontend, decide whether it is genuine. Deliberately narrow — this
package does not render the widget (that is the frontend's `VITE_`-keyed
site key, a pure client-side concern) and does not manage IP allow-lists
or bot scores beyond the single pass/fail Cloudflare's `siteverify`
endpoint returns.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from .types import TurnstileVerificationResult


@runtime_checkable
class TurnstileVerifier(Protocol):
    """Verify one Turnstile response token, server-side.

    A consumer calls this AFTER receiving `{"turnstile_token": "..."}` on
    a public form submission and BEFORE any side effect (gateway call, DB
    write) — a failed verification must short-circuit the request, never
    run alongside it.
    """

    async def verify(
        self, token: str, *, remote_ip: Optional[str] = None
    ) -> TurnstileVerificationResult:
        """Return whether `token` is a genuine, unconsumed Turnstile pass.

        Args:
            token: The `cf-turnstile-response` value the frontend widget
                produced (submitted by the consumer as `turnstile_token`).
            remote_ip: The caller's IP, when known — forwarded to
                Cloudflare's `siteverify` as an extra (non-authoritative)
                signal; omit when unavailable (e.g. behind a proxy that
                strips it).

        Returns:
            `TurnstileVerificationResult(success=False, ...)` for every
            failure mode (empty token, wrong secret, expired/already-used
            token, Cloudflare unreachable) — never raises for those. A
            consumer that needs to distinguish "network down" from
            "genuinely invalid" inspects `error_codes`/`raw`; the common
            case is a bare `if not result.success: raise 403`.
        """
        ...


__all__ = ["TurnstileVerifier"]
