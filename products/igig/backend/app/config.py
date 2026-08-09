"""
IgIg configuration.

Extends the framework's ProductSettings — minimal additions to support
the inherited skeletons (webhook receiver, etc.).
"""
from noctusai_seed import ProductSettings


class IgIgSettings(ProductSettings):
    """IgIg specific settings."""

    cors_origins: str = "@registry:own:igig"

    # ── Webhook receiver (consumed by app/routers/webhook_router.py) ──
    # Empty by default → ``webhook_endpoint(bypass_when_unset=True)``
    # accepts unsigned payloads with a WARNING (early-dev only). Set in
    # ``.env`` (``EXAMPLE_WEBHOOK_SECRET=…``) to enforce verification.
    # Rename per vendor (``resend_webhook_secret`` / ``meta_webhook_secret`` / etc.).
    example_webhook_secret: str = ""

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    webhook_rate_limit: str = "60/minute"

    # ── Domain persistence (development) ──────────────────────────────
    # IgIg's DOMAIN data lives in SQLite while the product is built; auth,
    # orgs and roles stay on Supabase via the seed's database module. The
    # swap to Supabase happens in `app/store.py`, not here.
    # Relative paths resolve against the backend working directory; the
    # containerised runtime mounts `var/` as a volume so the file survives
    # restarts.
    igig_sqlite_path: str = "var/igig.db"


settings = IgIgSettings()
