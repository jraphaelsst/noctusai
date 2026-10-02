"""
Store configuration.

Extends the framework's ProductSettings with the store's payment, delivery
and admin settings (contract `projects/store-v1-CONTRACT.md` §3 "Env").
Every value is read at request time through a FastAPI dependency
(`app/store_deps.py`), never captured at import.
"""
from noctusai_seed import ProductSettings

#: Asaas SANDBOX by default — production is an explicit opt-in via
#: `ASAAS_BASE_URL=https://api.asaas.com/v3`, never an accident.
ASAAS_SANDBOX_BASE_URL = "https://api-sandbox.asaas.com/v3"


class SeedSettings(ProductSettings):
    """Store specific settings."""

    cors_origins: str = "@registry:own:store"

    # ── Payments (seed `integrations.payments`, hosted one-off checkout) ──
    asaas_api_key: str = ""
    asaas_base_url: str = ASAAS_SANDBOX_BASE_URL
    # Asaas' webhook auth is a bare shared-secret token in the
    # `asaas-access-token` header. Unset => every delivery 401s (fail
    # closed — a financial webhook never has an early-dev bypass).
    asaas_webhook_token: str = ""
    # A missing Asaas key REFUSES checkout (503) unless this is explicitly
    # on. Test harness / local dev only: a silent Fake in a real deploy
    # would hand a paying buyer a fake checkout URL.
    payments_allow_fake: bool = False

    # ── Public site ──
    # Origin of the public storefront, no trailing slash. Builds the Asaas
    # `successUrl` (`{store_public_url}/obrigado?pedido={token}`) and the
    # download link in the delivery email.
    store_public_url: str = "https://store.noctusai.com"

    # ── Admin ──
    # Comma-separated emails (case-insensitive) allowed into /api/admin/*.
    # Empty => nobody is an admin (every admin route 403s).
    store_admin_emails: str = ""

    # ── Delivery email (seed `make_email_sender`, SMTP) ──
    # All four of host/port/username/password must be set for the Real
    # sender; otherwise the Fake sender is used ONLY when
    # `payments_allow_fake` is on — a real deploy with no SMTP records the
    # send failure on the pedido instead of pretending it delivered.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: str = "starttls"
    email_from: str = ""
    email_from_name: str = "Contrato Blindado"

    # ── Rate limits (per visitor IP; the public surface is unauthenticated) ──
    webhook_rate_limit: str = "60/minute"
    public_read_rate_limit: str = "120/minute"
    checkout_rate_limit: str = "10/minute;60/hour"
    download_rate_limit: str = "30/minute"


settings = SeedSettings()
