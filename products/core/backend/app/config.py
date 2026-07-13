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

    # SSO token TTL — LOAD-BEARING: read by the seed's
    # `noctusai_lib.api.auth.create_sso_token` (`settings.sso_token_expiration_minutes`)
    # when core mints a cross-product SSO token. `jwt_expiration_minutes`
    # (sibling field, dropped here) had no such consumer.
    sso_token_expiration_minutes: int = 5  # short-lived

    # CORS — registry-driven union of every product frontend (core hosts the SSO bridge).
    # `@registry:all` resolves at property-read time via
    # `noctusai_lib.config.cors_registry.derive_cors_origins(include_all_frontends=True)`,
    # parsing `start.sh PRODUCTS` between BEGIN/END_PRODUCTS_REGISTRY sentinels.
    # New product added to `start.sh` → automatically allowed here. See
    # `KB § PATTERNS/environment.md § CORS_ORIGINS cascade`. Replaces the
    # hand-enumerated 13-origin string from CORE-ORIGINS (commit 04534f7).
    # Wildcard `"*"` is forbidden here: seed factory wires allow_credentials=True,
    # and `*` + credentials is the MDN-documented auth-replay anti-pattern.
    cors_origins: str = "@registry:all"

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

    # Optional Postgres URL for SQLAlchemy-bound flows (audit-hook write side
    # effects for `public.tool_call_audits`). Empty → audit-hook lazy session
    # factory returns None and the audit writer skips with a debug log.
    # Routers/services use the Supabase admin client per `KB § PATTERNS/backend.md`
    # — the SQLAlchemy session is a SECONDARY surface, not the primary data path.
    # See `app/services/audit_hook.py` + `KB § PATTERNS/llm-tool-audit.md`.
    postgres_url: str = ""


settings = Settings()
