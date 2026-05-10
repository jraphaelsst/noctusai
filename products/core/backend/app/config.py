"""
NoctusAI Core — Configuration settings.

Extends the seed framework's `ProductSettings` so env_file resolution,
jwt_secret defaults, and the production safety validator come from the
single authoritative source. Only core-specific fields live here.
"""
from typing import Optional

from noctusai_seed import ProductSettings


class Settings(ProductSettings):
    """Core platform specific settings."""

    # JWT / SSO expirations (core-specific)
    jwt_expiration_minutes: int = 60 * 24  # 24h
    sso_token_expiration_minutes: int = 5  # short-lived

    # CORS — core accepts any origin (control-plane serves every product)
    cors_origins: str = "*"

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    app_base_url: str = "http://localhost:5173"

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    # Webhook-compliance pin #4 — see KB § PATTERNS/webhook-signatures.md.
    webhook_rate_limit: str = "60/minute"

    # Email (optional — Resend)
    resend_api_key: Optional[str] = None


settings = Settings()
