"""Cloudflare Turnstile verification — a small, reusable captcha seam.

**What this is.** One Protocol (`TurnstileVerifier`) + Fake + Real +
factory (`make_turnstile_verifier`), so any public, unauthenticated FastAPI
route can gate itself against bots with three lines: obtain the token the
frontend widget already produced, call `verify`, 403 on failure — no
per-product bespoke Cloudflare client.

**Why it lives here and not in a product.** The first consumer
(`products/community`'s public `POST /api/checkout`, module 2,
2026-09-16) needed anti-abuse on an unauthenticated endpoint that also
creates a real payment-gateway object per call — but Turnstile is a
generic "protect a public form" primitive with zero product-specific
vocabulary, exactly the kind of thing every future public form (the
existing `POST /api/aplicacoes`, any future signup/contact form) will
also want. Per `KB § 03-SEED-ARCHITECTURE.md`, a capability reusable by
more than one consumer belongs in the seed, not duplicated per-product.

**Recipe:**

    from noctusai_lib.integrations.turnstile import make_turnstile_verifier

    verifier = make_turnstile_verifier(secret=settings.community_turnstile_secret)
    result = await verifier.verify(payload.turnstile_token, remote_ip=request.client.host)
    if not result.success:
        raise http_error(403, "Verificação de segurança falhou. Recarregue a página e tente novamente.")

**Real adapter posture.** `RealTurnstileVerifier` calls Cloudflare's
`siteverify` REST endpoint directly (no SDK exists to wrap) and fails
CLOSED on any transport error — a network hiccup returns
`success=False`, never raises, never lets a bot through by accident.

**Fake adapter posture.** `FakeTurnstileVerifier` accepts any non-empty
token by default (`accept=True`); `accept=False` or `rejected_tokens`
simulate the failure branch. `make_turnstile_verifier` also returns the
Fake when no `secret` is configured — same early-dev-bypass affordance
the platform already uses for webhook secrets, EXCEPT an empty token
still 403s (only a configured-but-wrong secret is bypassed, never a
missing submission).
"""
from __future__ import annotations

from .factory import make_turnstile_verifier
from .fake import FakeTurnstileVerifier
from .protocol import TurnstileVerifier
from .real import RealTurnstileVerifier
from .types import TurnstileVerificationResult

__all__ = [
    "FakeTurnstileVerifier",
    "RealTurnstileVerifier",
    "TurnstileVerificationResult",
    "TurnstileVerifier",
    "make_turnstile_verifier",
]
