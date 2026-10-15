"""
Orbity configuration.

Extends the framework's ProductSettings with the WhatsApp (WAHA) wiring the
automation engine and the `Conexões WhatsApp` organ need. Every value reads
from the fleet `.env` (same names social-wiring uses — no new variable
ships for a fleet that already runs WhatsApp).
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Orbity specific settings."""

    cors_origins: str = "@registry:own:orbity"

    # Fernet key (fleet `ENCRYPTION_KEY`): encrypts each org's WAHA API key at
    # rest in `orbity.whatsapp_connections`. Empty => the connections organ
    # answers 503 and saved connections are ignored (static WAHA_* fallback).
    encryption_key: str = ""

    # Shared WAHA server (fleet `WAHA_BASE_URL` / `WAHA_API_KEY` / `WAHA_SESSION`).
    # `waha_base_url` is what a NEW connection is created against (the router
    # derives base_url/session server-side) and the static fallback when an
    # org has no saved connection. Empty AND no saved connection => sending
    # refuses with "WhatsApp não conectado" (never a silent Fake).
    waha_base_url: str = ""
    waha_api_key: str = ""
    waha_session: str = "default"
    waha_external_base_url: str = ""
    # Hex HMAC-SHA256 of the raw inbound body (header X-Webhook-Hmac-SHA256).
    # Unset => unsigned webhooks accepted (early-dev only), same as community.
    waha_webhook_hmac_secret: str = ""

    # Fake WAHA client ONLY under explicit opt-in (test harness / local dev,
    # WHATSAPP_ALLOW_FAKE=true). A Fake in a real deploy reported "sent" with
    # nothing sent (community, 2026-10-01).
    whatsapp_allow_fake: bool = False


settings = SeedSettings()
