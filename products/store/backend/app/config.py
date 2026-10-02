"""
Store configuration.

Extends the framework's ProductSettings with the store's payment, delivery
and admin settings (contract `projects/store-v1-CONTRACT.md` §3 "Env").
Every value is read at request time through a FastAPI dependency
(`app/store_deps.py`), never captured at import.
"""
from noctusai_seed import ProductSettings

#: Asaas environments. SANDBOX is the default — production is an explicit
#: choice the admin makes in the UI (`asaas_environment` key), never an accident.
ASAAS_SANDBOX_BASE_URL = "https://api-sandbox.asaas.com/v3"
ASAAS_PRODUCTION_BASE_URL = "https://api.asaas.com/v3"


class SeedSettings(ProductSettings):
    """Store specific settings."""

    cors_origins: str = "@registry:own:store"

    # ── Keys: DB-stored, NOT env (owner directive 2026-10-02) ──
    # Asaas key / webhook token / environment live Fernet-encrypted in
    # `store.credentials` (see app/api_keys.py); SMTP resolves through the
    # platform chain. Only these remain env:
    encryption_key: str = ""  # ENCRYPTION_KEY — Fernet key; unset => key writes 503
    # The owner's org: single-tenant scope every key is stored and resolved under.
    store_org_id: str = ""
    # A missing Asaas key REFUSES checkout (503) unless this is explicitly on.
    # Test harness / local dev only: a silent Fake in a real deploy would hand a
    # paying buyer a fake checkout URL.
    payments_allow_fake: bool = False

    # ── Public site ──
    # Origin of the public storefront, no trailing slash. Builds the Asaas
    # `successUrl` (`{store_public_url}/obrigado?pedido={token}`) and the
    # download link in the delivery email.
    store_public_url: str = "https://store.noctusai.com"

    # ── Admin ──
    # Comma-separated emails (case-insensitive) allowed into the admin routes.
    # Empty => nobody is an admin (every admin route 403s).
    store_admin_emails: str = ""

    # ── Rate limits (per visitor IP; the public surface is unauthenticated) ──
    webhook_rate_limit: str = "60/minute"
    public_read_rate_limit: str = "120/minute"
    checkout_rate_limit: str = "10/minute;60/hour"
    download_rate_limit: str = "30/minute"


settings = SeedSettings()
