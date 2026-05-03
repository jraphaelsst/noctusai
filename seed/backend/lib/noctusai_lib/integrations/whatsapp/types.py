"""WhatsApp inbound message value objects + payload errors.

Ported verbatim from `whatsapp-google-scheduling/app/services/waha/types.py`
2026-05-03 via `projects/whatsapp-seed-absorption/`. Provider-neutral
naming (`InboundMessage`, `Media`) preferred; the legacy `Waha*` aliases
are kept so call sites built against the sibling shape work without a
rename pass.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WhatsAppMedia:
    """Media attachment on an inbound WhatsApp message."""

    url: str | None
    mimetype: str | None


@dataclass(frozen=True)
class WhatsAppInboundMessage:
    """Parsed WhatsApp inbound message (provider-agnostic shape).

    Today populated by `parse_waha_inbound_message`; future Twilio /
    Cloud-API parsers populate the same shape.
    """

    provider_message_id: str | None
    chat_id: str
    from_phone: str
    text: str
    session: str
    media: WhatsAppMedia | None = None
    from_name: str | None = None


class WhatsAppPayloadError(ValueError):
    """Inbound payload failed validation (missing chat_id / no text or media)."""


class WhatsAppIgnoredEvent(ValueError):
    """Inbound payload is structurally valid but the event type / source
    is intentionally ignored (e.g. `session.status`, own-message echoes)."""


# Legacy WAHA-prefixed aliases (kept for call-site portability).
WahaMedia = WhatsAppMedia
WahaInboundMessage = WhatsAppInboundMessage
WahaPayloadError = WhatsAppPayloadError
WahaIgnoredEvent = WhatsAppIgnoredEvent
