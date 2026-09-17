"""
Community configuration.

Extends the framework's ProductSettings — minimal additions to support
the inherited skeletons (webhook receiver, etc.) plus module 2's
checkout / payments / Turnstile configuration.
"""
from noctusai_lib.integrations.payments.real_asaas import DEFAULT_BASE_URL as _ASAAS_DEFAULT_BASE_URL
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Community specific settings."""

    cors_origins: str = "@registry:own:community"

    # ── Webhook receiver (consumed by app/routers/webhook_router.py) ──
    # Empty by default → ``webhook_endpoint(bypass_when_unset=True)``
    # accepts unsigned payloads with a WARNING (early-dev only). Set in
    # ``.env`` (``EXAMPLE_WEBHOOK_SECRET=…``) to enforce verification.
    # Rename per vendor (``resend_webhook_secret`` / ``meta_webhook_secret`` / etc.).
    example_webhook_secret: str = ""

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    # Reused by BOTH module 2's payment webhooks (`/api/webhooks/stripe`,
    # `/api/webhooks/asaas` — contract amendment A9) and the inherited
    # `/api/webhooks/example` skeleton — same DDoS-guard rationale.
    webhook_rate_limit: str = "60/minute"

    # ── Public application form (contract §Aplicações, PUBLIC routes) ──
    # `GET /api/aplicacoes/formulario` and `POST /api/aplicacoes` are
    # genuinely unauthenticated — a human filling out a real form won't
    # hit this, so a tighter cap than the webhook default is fine.
    aplicacoes_rate_limit: str = "20/minute"

    # ── Module 2: payment gateways (community-m2-contract.md) ──
    # Reuses `noctusai_lib.integrations.payments` / `.checkout` verbatim —
    # no new gateway adapter. Empty defaults route both factories to
    # their Fake (see `app/services/checkout_service.py`'s
    # `_default_hosted_checkout_factory` / `_default_gateway`) — a fresh
    # clone boots and its tests pass with zero real credentials.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    asaas_api_key: str = ""
    asaas_base_url: str = _ASAAS_DEFAULT_BASE_URL
    # Asaas' webhook auth is a bare shared-secret token in the
    # `asaas-access-token` header (see `noctusai_lib.integrations.
    # payments.webhook_events`'s module docstring) — NOT a signature, so
    # naming this `_token` (not `_secret`) matches that module's own
    # `asaas_webhook_token` parameter name.
    asaas_webhook_token: str = ""

    # ── Module 2: public checkout — PUBLIC route, rate-limited
    # separately from the webhook/aplicacoes limiters above (contract
    # amendment A10) ──
    checkout_rate_limit: str = "20/minute"

    # Stripe's Checkout Session REQUIRES both `success_url`/`cancel_url`
    # (`StripeHostedCheckout.create_checkout` raises without either) —
    # the public `/assinar` page (contract §Frontend) is where the payer
    # lands either way; `?status=` lets the FE render the right state
    # without a server round-trip.
    frontend_base_url: str = "http://localhost:8210"

    # ── Module 2: abuse control (contract amendment A10 + product
    # decision P2) — config values, never literals in the service ──
    # Reuse an existing 'iniciada' Asaas subscription younger than this
    # many minutes instead of creating a second gateway object.
    checkout_reuse_window_minutes: int = 30
    checkout_max_per_email_per_24h: int = 5
    checkout_max_per_org_per_hour: int = 100

    # ── Module 2: Cloudflare Turnstile (product decision P2) ──
    # Empty by default → `make_turnstile_verifier` returns
    # `FakeTurnstileVerifier` (early-dev bypass, same posture as the
    # webhook secrets above) — a missing `turnstile_token` still 403s.
    community_turnstile_secret: str = ""


settings = SeedSettings()
