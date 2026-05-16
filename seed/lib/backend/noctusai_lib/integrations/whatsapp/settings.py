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
    external_base_url: str | None = None
    """Browser-facing host WAHA emits in media URLs (e.g.
    ``http://localhost:3000``). The app downloads media from
    ``base_url`` (docker-internal, e.g. ``http://waha:3000``) after
    rewriting. Defaults to ``base_url`` — set this ONLY when WAHA's
    emitted host differs from the host the app can reach (the docker
    deployment shape). See SESSION-NOTES §4.3 / workspace ``fedd4cf``."""
    webhook_hmac_secret: str | None = None
    """When set, inbound webhook router requires HMAC-SHA256 hex
    signature in `X-Webhook-Hmac-SHA256`. When None, the router
    skips signature verification (e.g. local dev, tunneled
    development WAHA without secrets configured)."""
