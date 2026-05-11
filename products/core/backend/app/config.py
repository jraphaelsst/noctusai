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

    # CORS — enumerated union of every product frontend (core hosts the SSO bridge).
    # See `projects/core-cors-origins-enumeration/PROJECT.md` for the origin map.
    # Wildcard `"*"` is forbidden here: seed factory wires allow_credentials=True,
    # and `*` + credentials is the MDN-documented auth-replay anti-pattern.
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080,http://localhost:8090,http://localhost:8095,http://localhost:8100,http://localhost:8110,http://localhost:8120,http://localhost:8123,http://localhost:8130,http://localhost:8140,http://localhost:8150,http://localhost:8160"

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
