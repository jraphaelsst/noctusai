"""WhatsApp inbound message value objects + payload errors.

Ported verbatim from `whatsapp-google-scheduling/app/services/waha/types.py`
2026-05-03 via `projects/whatsapp-seed-absorption/`. Provider-neutral
naming (`InboundMessage`, `Media`) preferred; the legacy `Waha*` aliases
are kept so call sites built against the sibling shape work without a
rename pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


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


@runtime_checkable
class WhatsAppClient(Protocol):
    """Send / download surface every WhatsApp connector implements.

    Both `WahaClient` (real, httpx-backed) and `FakeWahaClient`
    (in-memory deterministic) satisfy this Protocol naturally. Future
    Twilio / WhatsApp Cloud-API connectors land against the same shape.

    Per `KB § PATTERNS/seed-fake-real-adapter.md`: the Protocol is the
    contract that the gold-standard pattern's `get_<name>_adapter(...)`
    factory returns.
    """

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]: ...

    def send_text_sync(self, chat_id: str, text: str) -> dict[str, Any]: ...

    async def download_media(self, url: str) -> bytes: ...

    def download_media_sync(self, url: str) -> bytes: ...

    async def list_chats(self, limit: int = 50) -> list[dict[str, Any]]: ...

    async def fetch_chat_messages(
        self, chat_id: str, limit: int = 50
    ) -> list[dict[str, Any]]: ...


# Legacy WAHA-prefixed aliases (kept for call-site portability).
WahaMedia = WhatsAppMedia
WahaInboundMessage = WhatsAppInboundMessage
WahaPayloadError = WhatsAppPayloadError
WahaIgnoredEvent = WhatsAppIgnoredEvent
