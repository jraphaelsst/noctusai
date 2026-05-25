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

from noctusai_lib.integrations.whatsapp.client import WahaSessionNotReady
from noctusai_lib.integrations.whatsapp.types import (
    WhatsAppInboundMessage,
)

# 1x1 transparent PNG — deterministic stand-in for a real QR image so
# frontend/route tests can assert "bytes were served" without a browser.
_FAKE_QR_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
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
        # Session-admin state machine. Unpaired by default — mirrors a
        # fresh WAHA container before any QR scan.
        self.session_status: str = "SCAN_QR_CODE"
        self.me: dict[str, Any] | None = None
        self.webhook_config: dict[str, Any] | None = None
        self.restart_count = 0

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
    # Session admin — mirrors WahaClient session lifecycle / QR / webhook
    # ------------------------------------------------------------------

    async def get_session(self) -> dict[str, Any]:
        return {
            "name": self.session,
            "status": self.session_status,
            "me": self.me,
            "engine": {"engine": "FAKE"},
        }

    async def restart_session(self) -> dict[str, Any]:
        self.restart_count += 1
        # A restart drops an unpaired session back to QR; a paired one
        # (credentials would persist on a real WAHA volume) comes back up.
        if self.me is None:
            self.session_status = "SCAN_QR_CODE"
        else:
            self.session_status = "WORKING"
        return {"name": self.session, "status": self.session_status}

    async def logout_session(self) -> dict[str, Any]:
        self.me = None
        self.session_status = "SCAN_QR_CODE"
        return {"name": self.session, "status": self.session_status}

    async def get_qr(self) -> bytes:
        if self.session_status != "SCAN_QR_CODE":
            raise WahaSessionNotReady(status=self.session_status)
        return _FAKE_QR_PNG

    async def set_webhook(self, url: str, events: list[str]) -> dict[str, Any]:
        self.webhook_config = {"url": url, "events": list(events)}
        # Real WAHA restarts on config change; mirror the status churn.
        return {
            "name": self.session,
            "status": self.session_status,
            "config": {"webhooks": [self.webhook_config]},
        }

    def simulate_pair(
        self, *, phone: str = "5511999999999", push_name: str = "Fake"
    ) -> None:
        """Test helper: flip the fake to a paired/WORKING session."""
        self.me = {"id": f"{phone}@c.us", "pushName": push_name}
        self.session_status = "WORKING"

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
