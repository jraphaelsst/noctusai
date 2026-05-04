"""Deterministic in-memory WAHA client (no network).

Mirrors `WahaClient`'s send/download surface; adds bi-directional
`inject_inbound` + `sent_messages` for end-to-end test driving.

Use as the dev/local fallback when no `WAHA_BASE_URL` is configured,
or in tests as a deterministic stand-in. Same shape as
`google_maps.StaticRoutingAdapter` and `google_calendar.FakeCalendarAdapter`
per `KB § PATTERNS/seed-fake-real-adapter.md`.
"""

from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.whatsapp.types import (
    WhatsAppInboundMessage,
)


class FakeWahaClient:
    """In-memory WAHA stand-in. Records sent messages, serves
    pre-populated media, accepts injected inbound messages.

    Test pattern:
        client = FakeWahaClient()
        client.inject_text(chat_id="...", from_phone="...", text="...")
        # ... drive the consumer code that reads inbound_queue ...
        assert client.sent_messages[0]["text"] == "expected reply"
    """

    def __init__(self, *, session: str = "default"):
        self.session = session
        self.sent_messages: list[dict[str, Any]] = []
        self.inbound_queue: list[WhatsAppInboundMessage] = []
        self.media_bytes: dict[str, bytes] = {}

    # ------------------------------------------------------------------
    # Outbound — mirrors WahaClient.send_text / send_text_sync
    # ------------------------------------------------------------------

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        return self._record_send(chat_id, text)

    def send_text_sync(self, chat_id: str, text: str) -> dict[str, Any]:
        return self._record_send(chat_id, text)

    def _record_send(self, chat_id: str, text: str) -> dict[str, Any]:
        message_id = f"fake-msg-{len(self.sent_messages) + 1}"
        record = {
            "id": message_id,
            "session": self.session,
            "chatId": chat_id,
            "text": text,
        }
        self.sent_messages.append(record)
        return record

    # ------------------------------------------------------------------
    # Outbound — mirrors WahaClient.download_media / download_media_sync
    # ------------------------------------------------------------------

    async def download_media(self, url: str) -> bytes:
        return self._fetch_media(url)

    def download_media_sync(self, url: str) -> bytes:
        return self._fetch_media(url)

    def _fetch_media(self, url: str) -> bytes:
        if url not in self.media_bytes:
            raise KeyError(
                f"FakeWahaClient: no media pre-populated for url={url}. "
                "Call client.media_bytes[url] = b'...' before downloading."
            )
        return self.media_bytes[url]

    # ------------------------------------------------------------------
    # Bi-directional — test-driving inbound messages
    # ------------------------------------------------------------------

    def inject_inbound(self, message: WhatsAppInboundMessage) -> None:
        """Queue an inbound message as if WAHA delivered it via webhook.
        Consumers reading `inbound_queue` see messages in injection order."""
        self.inbound_queue.append(message)

    def inject_text(
        self,
        *,
        chat_id: str,
        from_phone: str,
        text: str,
        provider_message_id: str | None = None,
        from_name: str | None = None,
    ) -> WhatsAppInboundMessage:
        """Convenience: build + inject a text-only WhatsAppInboundMessage."""
        message = WhatsAppInboundMessage(
            provider_message_id=provider_message_id,
            chat_id=chat_id,
            from_phone=from_phone,
            text=text,
            session=self.session,
            from_name=from_name,
        )
        self.inject_inbound(message)
        return message

    def clear(self) -> None:
        """Reset between test cases."""
        self.sent_messages.clear()
        self.inbound_queue.clear()
        self.media_bytes.clear()
