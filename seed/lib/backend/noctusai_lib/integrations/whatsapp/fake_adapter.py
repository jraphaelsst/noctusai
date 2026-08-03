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

from noctusai_lib.integrations.whatsapp.client import (
    RECOVER_READY_STATUSES,
    WahaSessionNotReady,
    recovery_outcome,
)
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
        self.start_count = 0
        # When True, start_session/restart_session leave session_status
        # UNCHANGED (mirrors a real WAHA session whose STORED credentials
        # are dead: restart retries them and hangs, then WAHA force-stops
        # it back to the same status) — only logout_session (which clears
        # credentials) unsticks it. Set via simulate_stuck_session();
        # drives recover_session's full ladder to its "logout_start" rung.
        self.credentials_dead: bool = False
        # Capture the last payload passed to start/restart so tests can assert
        # the NOWEB store config is included.
        self.last_start_payload: dict[str, Any] | None = None
        self.last_restart_payload: dict[str, Any] | None = None
        # Pre-populated chat list for list_chats / fetch_chat_messages.
        # Seed via client.fake_chats[chat_id] = [msg_dict, ...] and
        # client.fake_chat_list = [chat_dict, ...].
        self.fake_chat_list: list[dict[str, Any]] = []
        self.fake_chat_messages: dict[str, list[dict[str, Any]]] = {}
        # Pre-populated overview list for get_chats_overview. Separate from
        # fake_chat_list because the real WAHA shapes differ: list_chats
        # returns raw chat objects, chats/overview returns pre-shaped
        # ChatSummary objects ({id, name, picture, lastMessage, _chat}).
        # Seed via client.fake_chats_overview = [{...}, ...].
        self.fake_chats_overview: list[dict[str, Any]] = []
        # Identity resolution: seed before calling get_contact/get_lid_phone/list_lids.
        self.fake_contacts: dict[str, dict[str, Any]] = {}
        self.fake_lid_phones: dict[str, str] = {}
        self.fake_lids: list[dict[str, Any]] = []
        # send_seen call log — assert against this to verify read-receipt calls.
        self.seen_calls: list[dict[str, Any]] = []

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

    async def send_seen(
        self,
        chat_id: str,
        message_id: str | None = None,
        participant: str | None = None,
    ) -> dict[str, Any]:
        """Record the call in ``seen_calls`` — mirrors WahaClient.send_seen.

        Assert against ``client.seen_calls`` for the exact call shape.
        """
        record: dict[str, Any] = {
            "session": self.session,
            "chatId": chat_id,
            "messageId": message_id,
            "participant": participant,
        }
        self.seen_calls.append(record)
        return {"success": True}

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

    async def start_session(self) -> dict[str, Any]:
        self.start_count += 1
        if self.credentials_dead:
            # Mirrors WAHA answering 409 "already started" on a session
            # that's genuinely stuck — nothing changes; the caller must
            # escalate (real start_session() already tolerates this 409).
            return {"name": self.session, "status": self.session_status}
        # Starting a fresh (unpaired) session puts it into SCAN_QR_CODE so
        # a QR is available; an already-paired session stays WORKING.
        if self.me is None:
            self.session_status = "SCAN_QR_CODE"
        return {"name": self.session, "status": self.session_status}

    async def restart_session(self) -> dict[str, Any]:
        self.restart_count += 1
        if self.credentials_dead:
            # Mirrors the live-fleet bug: restart retries the dead stored
            # credentials and hangs, then WAHA force-stops it back to the
            # same status — restart alone cannot recover this session.
            return {"name": self.session, "status": self.session_status}
        # A restart drops an unpaired session back to QR; a paired one
        # (credentials would persist on a real WAHA volume) comes back up.
        if self.me is None:
            self.session_status = "SCAN_QR_CODE"
        else:
            self.session_status = "WORKING"
        return {"name": self.session, "status": self.session_status}

    async def logout_session(self) -> dict[str, Any]:
        self.me = None
        self.credentials_dead = False
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

    async def recover_session(self, *, settle_seconds: float = 8.0) -> dict[str, Any]:
        """Deterministic mirror of ``WahaClient.recover_session``'s ladder.

        State transitions here happen synchronously through the same
        start/restart/logout state machine above (no real network, so no
        real settling time is needed) — ``settle_seconds`` is accepted
        for signature/Protocol parity but not actually waited on. Drive
        the FAILED-with-dead-credentials scenario via
        ``simulate_stuck_session()`` to exercise the full ladder down to
        the ``"logout_start"`` rung.
        """
        state = await self.get_session()
        if state.get("status") == "WORKING":
            return recovery_outcome(state, "already_working")

        state = await self.start_session()
        if state.get("status") in RECOVER_READY_STATUSES:
            return recovery_outcome(await self.get_session(), "start")

        state = await self.restart_session()
        if state.get("status") in RECOVER_READY_STATUSES:
            return recovery_outcome(await self.get_session(), "restart")

        await self.logout_session()
        await self.start_session()
        return recovery_outcome(await self.get_session(), "logout_start")

    # ------------------------------------------------------------------
    # Chat history — mirrors WahaClient.list_chats / fetch_chat_messages
    # ------------------------------------------------------------------

    async def list_chats(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return ``fake_chat_list[:limit]``.

        Seed via ``client.fake_chat_list = [{...}, ...]`` before the call
        to simulate a WAHA store that already has history.
        """
        return self.fake_chat_list[:limit]

    async def get_chats_overview(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return ``fake_chats_overview[:limit]``.

        Seed via ``client.fake_chats_overview = [{"id": ..., "name": ...,
        "picture": ..., "lastMessage": {...}, "_chat": {...}}, ...]``.
        """
        return self.fake_chats_overview[:limit]

    async def fetch_chat_messages(
        self, chat_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return ``fake_chat_messages[chat_id][:limit]``.

        Seed via ``client.fake_chat_messages[chat_id] = [{...}, ...]``.
        """
        return self.fake_chat_messages.get(chat_id, [])[:limit]

    # ------------------------------------------------------------------
    # Identity resolution — mirrors WahaClient.get_contact/get_lid_phone/list_lids
    # ------------------------------------------------------------------

    async def get_contact(self, contact_id: str) -> dict[str, Any]:
        """Return ``fake_contacts[contact_id]`` or ``{}`` if not seeded.

        Seed via ``client.fake_contacts["5511@c.us"] = {"id": ..., "name": ...}``.
        """
        return self.fake_contacts.get(contact_id, {})

    async def get_lid_phone(self, lid: str) -> str | None:
        """Return ``fake_lid_phones[lid]`` or ``None`` if not seeded.

        Seed via ``client.fake_lid_phones["33613018058989@lid"] = "5511974693365@c.us"``.
        """
        return self.fake_lid_phones.get(lid)

    async def list_lids(self) -> list[dict[str, Any]]:
        """Return ``fake_lids``.

        Seed via ``client.fake_lids = [{"lid": "...", "pn": "..@c.us"}, ...]``.
        """
        return list(self.fake_lids)

    def simulate_pair(
        self, *, phone: str = "5511999999999", push_name: str = "Fake"
    ) -> None:
        """Test helper: flip the fake to a paired/WORKING session."""
        self.me = {"id": f"{phone}@c.us", "pushName": push_name}
        self.session_status = "WORKING"

    def simulate_stuck_session(
        self,
        *,
        status: str = "FAILED",
        phone: str = "5511999999999",
        push_name: str = "Stuck",
    ) -> None:
        """Test helper: put the fake into the paired-but-dead-credentials
        stuck state ``recover_session``'s ladder exists to recover from
        (mirrors the live fleet bug: stored creds, ``restart`` retries
        them and hangs, only ``logout`` clears them). ``start_session``
        and ``restart_session`` become no-ops (status stays ``status``)
        until ``logout_session`` runs.
        """
        self.me = {"id": f"{phone}@c.us", "pushName": push_name}
        self.session_status = status
        self.credentials_dead = True

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
        self.fake_chat_list.clear()
        self.fake_chat_messages.clear()
        self.fake_chats_overview.clear()
        self.fake_contacts.clear()
        self.fake_lid_phones.clear()
        self.fake_lids.clear()
        self.seen_calls.clear()
