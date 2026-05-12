"""Canonical named rate-limit policies for NoctusAI product routers.

**Why named, not literal.** Until 2026-05-11, every product hard-coded
slowapi rate-limit decorators with bare string literals
(``@limiter.limit("30/minute")``). The same value appeared across N=10+
product router files for the same intent — AI/LLM endpoints, post-auth
mutations, WhatsApp webhook receivers, public-portal reads. When the
team wants to tune one of those buckets (e.g. relax AI to 60/minute
during a billing test, or tighten portal endpoints after a probe),
N=10+ files have to change — and there's no way to read the literal
``"30/minute"`` and know which bucket it belongs to.

**The fix is intent-encoding.** These constants name the *policy*
(``DEFAULT_AI_RL``, ``DEFAULT_AUTH_RL``, ``DEFAULT_WEBHOOK_RL``,
``DEFAULT_PORTAL_RL``) rather than the value (``"30/minute"``). Per-
product tuning becomes a one-line change at the seed — every consumer
inherits automatically. The same string today (``"30/minute"``) MAY
diverge tomorrow without forcing N=10+ commits.

**Triggered by the recurrence rule (N≥3 → MUST formalize).** Confirmed
callsites at lift time (2026-05-11): 10 product router files, ~30+
decorator instances. See `KB § PATTERNS/project-execution.md § 2.7`
for the recurrence rule body, and ``feedback_recurrence_rule.md`` for
the slip-history that motivated the rule.

**Usage:**

    from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL

    @router.post("/generate")
    @limiter.limit(DEFAULT_AI_RL)
    async def generate(...): ...

**Format invariant.** Every constant value MUST be a valid slowapi
limit string of shape ``"<int>/<window>"`` where ``<window>`` is one
of ``second / minute / hour / day``. The regression test in
``seed/lib/backend/tests/api/test_rate_limit_policies.py`` enforces
this — if a tuning change accidentally breaks the shape, CI catches
it before any product picks it up.
"""
from __future__ import annotations

# AI / LLM-touching endpoints — generation, completion, embedding,
# transcription. Bucket sized for interactive-UI cadence; relax/tighten
# here when LLM cost or upstream-vendor rate-limits shift.
DEFAULT_AI_RL: str = "30/minute"

# Auth / onboarding / session-management endpoints touched post-login
# (not the pre-auth password/OTP flows — those use stricter per-product
# limits in the 5-10/minute range and stay literal until N≥3 surfaces).
DEFAULT_AUTH_RL: str = "30/minute"

# Webhook receivers — inbound from external vendors (WhatsApp/WAHA,
# payment providers, calendar callbacks). Pairs with the 5-pin webhook
# compliance contract (`KB § PATTERNS/webhook-signatures.md`).
DEFAULT_WEBHOOK_RL: str = "30/minute"

# Public-portal endpoints — token-gated reads/writes from end-clients
# (portal_cliente, portal_externo). Slightly looser than AI because
# the per-token tenant scope is narrower than per-IP.
DEFAULT_PORTAL_RL: str = "30/minute"


__all__ = [
    "DEFAULT_AI_RL",
    "DEFAULT_AUTH_RL",
    "DEFAULT_WEBHOOK_RL",
    "DEFAULT_PORTAL_RL",
]
