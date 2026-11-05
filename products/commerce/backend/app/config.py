"""
Commerce configuration.

Extends the framework's ProductSettings — minimal additions to support
the inherited skeletons (webhook receiver, etc.).
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Commerce specific settings."""

    cors_origins: str = "@registry:own:commerce"

    # ── Webhook receiver (consumed by app/routers/webhook_router.py) ──
    # Empty by default → ``webhook_endpoint(bypass_when_unset=True)``
    # accepts unsigned payloads with a WARNING (early-dev only). Set in
    # ``.env`` (``EXAMPLE_WEBHOOK_SECRET=…``) to enforce verification.
    # Rename per vendor (``resend_webhook_secret`` / ``meta_webhook_secret`` / etc.).
    example_webhook_secret: str = ""

    # ── Commerce organ ──
    # Fernet key for the per-org Asaas credentials (`commerce.credentials`).
    # Unset => key WRITES 503 (never plaintext); READS degrade to the platform chain.
    encryption_key: str = ""
    # HMAC secret that signs the e-mailed access / privacy-verify links
    # (resolved per request; unset => those routes 503, never an unsigned link).
    commerce_link_secret: str = ""
    # A missing Asaas key / SMTP config REFUSES (503) unless this is explicitly on.
    # Test harness / local dev only: a silent Fake in a real deploy would hand a
    # paying buyer a fake checkout URL.
    payments_allow_fake: bool = False
    # Invoices (NFS-e / NF-e via Focus NFe). The provider TOKEN is a platform credential
    # (`focusnfe_token`: org -> platform_settings -> env FOCUSNFE_TOKEN, via `resolve_credential`);
    # an absent token REFUSES (503) unless this is explicitly on -- test harness / local dev only,
    # a silent Fake in a real deploy would "issue" notes that never reach the tax authority.
    # Production additionally needs env FOCUSNFE_ALLOW_PRODUCTION=1 + platform credential
    # `focusnfe_environment=producao` (+ `focusnfe_token_environment`).
    invoices_allow_fake: bool = False
    # Origin the Asaas readiness probe uses as `successUrl`.
    commerce_public_url: str = "https://commerce.noctusai.com"

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    webhook_rate_limit: str = "60/minute"


settings = SeedSettings()
