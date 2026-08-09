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

    # ── Cofre de Acessos (Módulo 2) ───────────────────────────────────
    # Fernet key for client credentials at rest. Deliberately EMPTY by
    # default: with no key the vault refuses to store a password rather than
    # silently falling back to plaintext. Generate with
    # `noctusai_lib.security.encrypted_tokens.generate_key()` and keep it
    # OUT-OF-BAND from the database — a key stored beside the ciphertext
    # protects nothing.
    igig_cofre_key: str = ""

    # ── Visual assets (Módulo 4 portal) ───────────────────────────────
    # "supabase" in production; "local" for native dev; "fake" in tests.
    igig_storage_kind: str = "supabase"
    igig_storage_root: str = "var/assets"
    igig_storage_bucket: str = "igig"

    # ── Canais sociais (Módulo 5) ─────────────────────────────────────
    # Env-level FALLBACK only. The real path is a per-org credential stored
    # encrypted in `igig.integracao` and set through the Integrações screen —
    # an agency serves many clients' accounts, so one global token per channel
    # cannot be the primary model. Empty ⇒ the publisher stays the Fake and
    # nothing is ever reported as published.
    igig_meta_token: str = ""
    igig_tiktok_token: str = ""
    igig_linkedin_token: str = ""


settings = IgIgSettings()
