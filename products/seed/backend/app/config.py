"""
Seed Product configuration.

Extends the framework's ProductSettings — minimal additions to support
the inherited skeletons (webhook receiver, etc.).
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Seed Product specific settings."""

    cors_origins: str = "http://localhost:8004,http://localhost:8100,http://localhost:5173,http://localhost:3000"

    # ── Webhook receiver (consumed by app/routers/webhook_router.py) ──
    # Empty by default → ``webhook_endpoint(bypass_when_unset=True)``
    # accepts unsigned payloads with a WARNING (early-dev only). Set in
    # ``.env`` (``EXAMPLE_WEBHOOK_SECRET=…``) to enforce verification.
    # Rename per vendor (``resend_webhook_secret`` / ``meta_webhook_secret`` / etc.).
    example_webhook_secret: str = ""

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    webhook_rate_limit: str = "60/minute"


settings = SeedSettings()
