"""WhatsApp module Pydantic Settings.

Pulled by `configure_whatsapp_module(...)` from a product's settings.
Only the fields the WhatsApp module needs; product code injects them
at boot.
"""

from __future__ import annotations

from pydantic import BaseModel


class WhatsAppSettings(BaseModel):
    """Configuration the WhatsApp module needs.

    Build from a product's settings:

        whatsapp_settings = WhatsAppSettings(
            base_url=settings.waha_base_url,
            api_key=settings.waha_api_key,
            session=settings.waha_session,
            webhook_hmac_secret=settings.waha_webhook_hmac_secret,
        )
    """

    base_url: str
    api_key: str | None = None
    session: str = "default"
    webhook_hmac_secret: str | None = None
    """When set, inbound webhook router requires HMAC-SHA256 hex
    signature in `X-Webhook-Hmac-SHA256`. When None, the router
    skips signature verification (e.g. local dev, tunneled
    development WAHA without secrets configured)."""
