"""Tests for whatsapp_router.py — the WAHA webhook receiver.

Slice 4 (whatsapp-realtime-inbox, 2026-08-03) rewrote this router to make
Postgres the read source of truth for the chat inbox. Coverage:

  - HMAC signature verification (the 5-pin webhook_endpoint contract):
    valid → 200, tampered → 401, missing header → 401, unset secret →
    200 + WARNING bypass. Status-code-pinned per
    ``KB § PATTERNS/compliance/auth-boundary-false-green.md``.
  - Event dispatch: message.ack applied to the right row (+ unknown-id
    no-op), message.reaction acknowledged without erroring,
    session.status persisted + published.
  - message/message.any: chat_id populated, the realtime bus receives
    message.new with the exact MessageDTO contract shape.
  - Backfill-adjacent drift-found: the pre-existing contact
    auto-registration bug (``connection.encrypted_api_key`` — a field
    that never existed on ``WhatsAppConnectionRecord``) is exercised
    indirectly (it must no longer raise on every inbound).

MockSupabaseClient's ``upsert()`` does not propagate writes into the
shared row list (documented limitation in ``noctusai_lib/testing/mocks.py``
— "Upsert propagation is deferred to a follow-up project"), so
``WhatsAppChatStore.record_message`` cannot be round-tripped through the
mock. The chat.upsert test below substitutes a small recording fake for
``WhatsAppChatStore`` instead — it verifies THIS router calls the
collaborator with the right arguments, not the peer-owned store's
internals (that belongs in the peer's own test file). See the delivery
footer's ``drift-found:`` for the platform-wide implication.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from noctusai_lib.realtime import FakeRealtimeBus
from noctusai_lib.testing import MockSupabaseClient, bind_consent_module_to_mock

from app.config import settings
from app.services.whatsapp_chat_store import ChatSummary
from app.services.whatsapp_realtime import (
    EVENT_CHAT_UPSERT,
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_NEW,
    EVENT_SESSION_STATUS,
)

_ORG_ID = "00000000-0000-4000-8000-0000000000e1"
_USER_ID = "00000000-0000-4000-8000-0000000000e2"
_CONNECTION_ID = "00000000-0000-4000-8000-0000000000e3"
_WEBHOOK_TOKEN = "test-webhook-token-abc"
_AUTHORIZED_SENDER = "+5511999990000"
_CHAT_ID = "5511999990000@c.us"


def _sig(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _message_payload(
    *,
    event: str = "message",
    chat_id: str = _CHAT_ID,
    body: str = "oi",
    msg_id: str = "msg-1",
    from_me: bool = False,
    ack: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": msg_id,
        "timestamp": 1722700000,
        "from": chat_id,
        "chatId": chat_id,
        "body": body,
        "fromMe": from_me,
    }
    if ack is not None:
        payload["ack"] = ack
    return {"event": event, "session": "default", "payload": payload}


def _session_status_payload(status: str = "WORKING") -> dict[str, Any]:
    return {
        "event": "session.status",
        "session": "default",
        "payload": {"status": status, "statuses": []},
    }


def _reaction_payload() -> dict[str, Any]:
    return {
        "event": "message.reaction",
        "session": "default",
        "payload": {
            "id": "reaction-evt-1",
            "from": _CHAT_ID,
            "fromMe": False,
            "reaction": {"text": "👍", "messageId": "msg-1"},
        },
    }


# ─── Schema-caching client — recurrence N=3 with test_ads_router.py /
# test_ig_insights.py's copy of the same shape (their own delivery
# footers already flagged N=2; this makes it 3 — MUST-formalize
# territory, see the scoped-improvement below). Needed here because the
# plain `client` fixture's `mock_sb.schema(...)` builds a FRESH scoped
# client on every call (verified empirically), so writes from one
# request are invisible to a later request/read without this cache. ────
class _SchemaCachingClient:
    def __init__(self, root: MockSupabaseClient) -> None:
        self._root = root
        self._scoped: dict[str, Any] = {}

    def schema(self, name: str):
        if name not in self._scoped:
            self._scoped[name] = self._root.schema(name)
        return self._scoped[name]

    def __getattr__(self, item):
        return getattr(self._root, item)


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    caching = _SchemaCachingClient(mock_sb)

    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=caching),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield tc, mock_sb, caching


@pytest.fixture(autouse=True)
def _webhook_settings(monkeypatch):
    """Deterministic settings for every test in this module — independent
    of whatever the developer's/CI's root .env carries.

    A valid ``encryption_key`` is required for the token-scoped route's
    ``get_token_webhook_store`` DI seam to resolve at all (an unset key
    → 404, per the router's own config-gap handling); everything else
    steers the message/message.any flow to the cheap
    ``intake.handle_message`` no-reply path so tests don't depend on
    OpenAI/YouTube/CRM credentials.
    """
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "waha_webhook_hmac_secret", "")
    monkeypatch.setattr(settings, "whatsapp_chatbot_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "crm_base_url", "")
    monkeypatch.setattr(settings, "crm_api_key", "")
    monkeypatch.setattr(settings, "vista_base_url", "")
    monkeypatch.setattr(settings, "vista_api_key", "")
    monkeypatch.setattr(settings, "whatsapp_authorized_numbers", _AUTHORIZED_SENDER)


def _seed_connection(
    db,
    *,
    connection_id: str = _CONNECTION_ID,
    org_id: str = _ORG_ID,
    user_id: str = _USER_ID,
    token: str = _WEBHOOK_TOKEN,
    authorized_numbers: list[str] | None = None,
    bound_chats: list[dict] | None = None,
    auto_reply_enabled: bool = False,
) -> None:
    fernet = Fernet(settings.encryption_key.encode("utf-8"))
    encrypted = fernet.encrypt(b"fake-waha-api-key").decode("ascii")
    db.schema("social_wiring").set_table_data(
        "whatsapp_connections",
        [
            {
                "id": connection_id,
                "org_id": org_id,
                "user_id": user_id,
                "label": "Test line",
                "base_url": "https://waha.example.com",
                "session_name": "default",
                "encrypted_api_key": encrypted,
                "webhook_url": None,
                "webhook_token": token,
                "auto_reply_enabled": auto_reply_enabled,
                "authorized_numbers": authorized_numbers or [],
                "bound_chats": bound_chats or [],
                "client_id": None,
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-01T00:00:00Z",
            }
        ],
    )


def _find_message(db, provider_message_id: str) -> dict[str, Any] | None:
    resp = (
        db.schema("social_wiring")
        .table("conversation_messages")
        .select("*")
        .eq("provider_message_id", provider_message_id)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


class _RecordingChatStore:
    """Stand-in for WhatsAppChatStore — see the module docstring for why
    the real store can't round-trip through MockSupabaseClient. Verifies
    whatsapp_router calls ``record_message`` with the right arguments and
    returns a real ``ChatSummary`` so the chat.upsert bus-publish path is
    exercised end-to-end too."""

    calls: list[dict[str, Any]] = []

    def __init__(self, *, admin_supabase, org_id):
        self.org_id = org_id

    def record_message(self, **kwargs):
        _RecordingChatStore.calls.append(kwargs)
        return ChatSummary(
            chat_id=kwargs["chat_id"],
            title=kwargs.get("title") or kwargs["chat_id"],
            last_message_at=kwargs["created_at"],
            last_message_preview=(kwargs.get("body") or "")[:140],
            last_direction=kwargs["direction"],
            unread_count=1,
            last_read_at=None,
            archived=False,
            pinned=False,
        )


@pytest.fixture(autouse=True)
def _reset_recording_chat_store():
    _RecordingChatStore.calls = []
    yield
    _RecordingChatStore.calls = []


# ── Signature verification (legacy global route) ───────────────────────────

class TestWebhookSignatureVerification:
    def test_valid_signature_returns_200(self, client, monkeypatch):
        tc, _mock_sb, _db = client
        monkeypatch.setattr(settings, "waha_webhook_hmac_secret", "sekrit")
        body = b'{"event":"session.status","session":"default","payload":{"status":"WORKING"}}'
        resp = tc.post(
            "/api/whatsapp/webhook",
            content=body,
            headers={
                "X-Webhook-Hmac-SHA256": _sig(body, "sekrit"),
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200

    def test_tampered_body_returns_401(self, client, monkeypatch):
        tc, _mock_sb, _db = client
        monkeypatch.setattr(settings, "waha_webhook_hmac_secret", "sekrit")
        signed_body = b'{"event":"session.status","session":"default","payload":{"status":"A"}}'
        sig = _sig(signed_body, "sekrit")
        resp = tc.post(
            "/api/whatsapp/webhook",
            content=b'{"event":"session.status","session":"default","payload":{"status":"B"}}',
            headers={"X-Webhook-Hmac-SHA256": sig, "content-type": "application/json"},
        )
        assert resp.status_code == 401

    def test_missing_signature_header_returns_401(self, client, monkeypatch):
        tc, _mock_sb, _db = client
        monkeypatch.setattr(settings, "waha_webhook_hmac_secret", "sekrit")
        resp = tc.post(
            "/api/whatsapp/webhook",
            content=b'{"event":"session.status","session":"default","payload":{}}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 401

    def test_unset_secret_bypasses_with_warning(self, client, monkeypatch, caplog):
        import logging

        tc, _mock_sb, _db = client
        monkeypatch.setattr(settings, "waha_webhook_hmac_secret", "")
        with caplog.at_level(logging.WARNING, logger="noctusai_lib.security.webhook_signatures"):
            resp = tc.post(
                "/api/whatsapp/webhook",
                content=b'{"event":"session.status","session":"default","payload":{}}',
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 200
        assert any(
            "bypass" in r.message.lower() or "unset" in r.message.lower()
            for r in caplog.records
        ), "expected the bypass WARNING in the log"

    def test_invalid_json_after_valid_signature_returns_200(self, client, monkeypatch):
        """WAHA must never see a non-200 for a body it sent — even if the
        JSON is malformed post-verification, the router 200-acks and
        drops it (never retried forever)."""
        tc, _mock_sb, _db = client
        monkeypatch.setattr(settings, "waha_webhook_hmac_secret", "sekrit")
        body = b"not-json{"
        resp = tc.post(
            "/api/whatsapp/webhook",
            content=body,
            headers={
                "X-Webhook-Hmac-SHA256": _sig(body, "sekrit"),
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200


class TestTokenRouteResolution:
    def test_unknown_token_returns_404(self, client):
        tc, _mock_sb, _db = client
        resp = tc.post(
            "/api/whatsapp/webhook/unknown-token",
            content=b'{"event":"session.status","session":"default","payload":{}}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 404

    def test_known_token_valid_signature_returns_200(self, client, monkeypatch):
        tc, _mock_sb, db = client
        _seed_connection(db)
        monkeypatch.setattr(settings, "waha_webhook_hmac_secret", "sekrit")
        body = b'{"event":"session.status","session":"default","payload":{"status":"WORKING"}}'
        resp = tc.post(
            f"/api/whatsapp/webhook/{_WEBHOOK_TOKEN}",
            content=body,
            headers={
                "X-Webhook-Hmac-SHA256": _sig(body, "sekrit"),
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200

    def test_known_token_tampered_body_returns_401(self, client, monkeypatch):
        tc, _mock_sb, db = client
        _seed_connection(db)
        monkeypatch.setattr(settings, "waha_webhook_hmac_secret", "sekrit")
        signed_body = b'{"event":"session.status","session":"default","payload":{"status":"A"}}'
        sig = _sig(signed_body, "sekrit")
        resp = tc.post(
            f"/api/whatsapp/webhook/{_WEBHOOK_TOKEN}",
            content=b'{"event":"session.status","session":"default","payload":{"status":"B"}}',
            headers={"X-Webhook-Hmac-SHA256": sig, "content-type": "application/json"},
        )
        assert resp.status_code == 401


# ── session.status ──────────────────────────────────────────────────────────

class TestSessionStatus:
    def test_legacy_route_persists_to_redis(self, client):
        import redis as redis_lib

        tc, _mock_sb, _db = client
        resp = tc.post("/api/whatsapp/webhook", json=_session_status_payload("SCAN_QR_CODE"))
        assert resp.status_code == 200

        r = redis_lib.from_url(settings.redis_url, decode_responses=True)
        try:
            assert r.get("whatsapp:session_status:default") == "SCAN_QR_CODE"
        finally:
            r.delete("whatsapp:session_status:default")

    def test_token_route_persists_and_publishes(self, client, monkeypatch):
        import redis as redis_lib

        tc, _mock_sb, db = client
        _seed_connection(db)
        fake_bus = FakeRealtimeBus()
        monkeypatch.setattr(
            "app.routers.whatsapp_router.get_whatsapp_bus", lambda _url: fake_bus
        )

        resp = tc.post(
            f"/api/whatsapp/webhook/{_WEBHOOK_TOKEN}",
            json=_session_status_payload("WORKING"),
        )
        assert resp.status_code == 200

        r = redis_lib.from_url(settings.redis_url, decode_responses=True)
        key = f"whatsapp:session_status:{_CONNECTION_ID}"
        try:
            assert r.get(key) == "WORKING"
        finally:
            r.delete(key)

        scope = f"wa:conn:{_CONNECTION_ID}"
        events = fake_bus._streams.get(scope, [])
        assert any(e.event == EVENT_SESSION_STATUS for e in events)
        published = next(e for e in events if e.event == EVENT_SESSION_STATUS)
        assert published.payload == {"status": "WORKING", "session": "default"}


# ── message.ack ──────────────────────────────────────────────────────────

class TestMessageAck:
    def test_ack_applies_to_matching_row(self, client, monkeypatch):
        tc, _mock_sb, db = client
        _seed_connection(db, authorized_numbers=[])
        fake_bus = FakeRealtimeBus()
        monkeypatch.setattr(
            "app.routers.whatsapp_router.get_whatsapp_bus", lambda _url: fake_bus
        )
        monkeypatch.setattr(
            "app.routers.whatsapp_router.WhatsAppChatStore", _RecordingChatStore
        )

        # Unique per test run — the Redis SETNX dedup key this `message`
        # event sets carries a 5-minute TTL in REAL local Redis (this
        # suite's convention, per conftest.py), so a hardcoded literal id
        # re-used across two test runs within that window would make the
        # SECOND run's `message` event look like a duplicate and silently
        # skip the insert this test depends on.
        msg_id = f"ack-target-{uuid4().hex[:8]}"

        # First: an inbound message lands (creates the row the ack targets).
        resp = tc.post(
            f"/api/whatsapp/webhook/{_WEBHOOK_TOKEN}",
            json=_message_payload(msg_id=msg_id, body="oi"),
        )
        assert resp.status_code == 200
        assert _find_message(db, msg_id) is not None

        # Then: the ack for it.
        resp = tc.post(
            f"/api/whatsapp/webhook/{_WEBHOOK_TOKEN}",
            json=_message_payload(event="message.ack", msg_id=msg_id, ack=3),
        )
        assert resp.status_code == 200

        row = _find_message(db, msg_id)
        assert row is not None
        assert row["ack"] == 3
        assert row["acked_at"]

        scope = f"wa:conn:{_CONNECTION_ID}"
        events = fake_bus._streams.get(scope, [])
        ack_events = [e for e in events if e.event == EVENT_MESSAGE_ACK]
        assert len(ack_events) == 1
        assert ack_events[0].payload["provider_message_id"] == msg_id
        assert ack_events[0].payload["ack"] == 3
        assert ack_events[0].payload["chat_id"] == _CHAT_ID

    def test_ack_for_unknown_message_is_a_no_op(self, client, monkeypatch):
        tc, _mock_sb, db = client
        _seed_connection(db, authorized_numbers=[])
        fake_bus = FakeRealtimeBus()
        monkeypatch.setattr(
            "app.routers.whatsapp_router.get_whatsapp_bus", lambda _url: fake_bus
        )

        resp = tc.post(
            f"/api/whatsapp/webhook/{_WEBHOOK_TOKEN}",
            json=_message_payload(event="message.ack", msg_id="never-recorded", ack=1),
        )
        assert resp.status_code == 200

        scope = f"wa:conn:{_CONNECTION_ID}"
        events = fake_bus._streams.get(scope, [])
        assert not any(e.event == EVENT_MESSAGE_ACK for e in events)


# ── message.reaction ─────────────────────────────────────────────────────

class TestMessageReaction:
    def test_reaction_is_acknowledged_not_persisted(self, client):
        tc, _mock_sb, db = client
        before = (
            db.schema("social_wiring").table("conversation_messages").select("*").execute()
        )
        resp = tc.post("/api/whatsapp/webhook", json=_reaction_payload())
        assert resp.status_code == 200
        after = (
            db.schema("social_wiring").table("conversation_messages").select("*").execute()
        )
        assert len(after.data or []) == len(before.data or [])


# ── message / message.any ────────────────────────────────────────────────

class TestInboundMessage:
    def test_persists_with_chat_id_and_publishes_message_new(self, client, monkeypatch):
        tc, _mock_sb, db = client
        _seed_connection(db, authorized_numbers=[])
        fake_bus = FakeRealtimeBus()
        monkeypatch.setattr(
            "app.routers.whatsapp_router.get_whatsapp_bus", lambda _url: fake_bus
        )
        monkeypatch.setattr(
            "app.routers.whatsapp_router.WhatsAppChatStore", _RecordingChatStore
        )

        msg_id = f"new-msg-{uuid4().hex[:8]}"  # unique — see ack test's comment
        resp = tc.post(
            f"/api/whatsapp/webhook/{_WEBHOOK_TOKEN}",
            json=_message_payload(msg_id=msg_id, body="oi tudo bem"),
        )
        assert resp.status_code == 200

        row = _find_message(db, msg_id)
        assert row is not None
        assert row["chat_id"] == _CHAT_ID
        assert row["connection_id"] == _CONNECTION_ID

        # WhatsAppChatStore.record_message was called with the right shape.
        assert len(_RecordingChatStore.calls) == 1
        call = _RecordingChatStore.calls[0]
        assert call["chat_id"] == _CHAT_ID
        assert call["direction"] == "inbound"
        assert call["body"] == "oi tudo bem"
        assert call["connection_id"] == UUID(_CONNECTION_ID)

        scope = f"wa:conn:{_CONNECTION_ID}"
        events = fake_bus._streams.get(scope, [])
        new_events = [e for e in events if e.event == EVENT_MESSAGE_NEW]
        assert len(new_events) == 1
        dto = new_events[0].payload["message"]
        assert new_events[0].payload["chat_id"] == _CHAT_ID
        assert dto["provider_message_id"] == msg_id
        assert dto["chat_id"] == _CHAT_ID
        assert dto["direction"] == "inbound"
        assert dto["body"] == "oi tudo bem"
        assert set(dto.keys()) == {
            "id", "provider_message_id", "chat_id", "direction", "body",
            "ack", "acked_at", "created_at", "structured_payload",
        }

        upsert_events = [e for e in events if e.event == EVENT_CHAT_UPSERT]
        assert len(upsert_events) == 1
        assert upsert_events[0].payload["chat_id"] == _CHAT_ID

    def test_message_any_duplicate_of_message_is_dropped_via_setnx(self, client, monkeypatch):
        """The message/message.any race: WAHA fires both for the same
        send. The Redis SETNX pre-filter catches the second one before
        any DB work."""
        tc, _mock_sb, db = client
        _seed_connection(db, authorized_numbers=[])
        monkeypatch.setattr(
            "app.routers.whatsapp_router.WhatsAppChatStore", _RecordingChatStore
        )

        msg_id = f"race-msg-{uuid4().hex[:8]}"  # unique — see ack test's comment
        first = tc.post(
            f"/api/whatsapp/webhook/{_WEBHOOK_TOKEN}",
            json=_message_payload(event="message", msg_id=msg_id),
        )
        assert first.status_code == 200
        second = tc.post(
            f"/api/whatsapp/webhook/{_WEBHOOK_TOKEN}",
            json=_message_payload(event="message.any", msg_id=msg_id),
        )
        assert second.status_code == 200

        rows = (
            db.schema("social_wiring")
            .table("conversation_messages")
            .select("*")
            .eq("provider_message_id", msg_id)
            .execute()
        )
        assert len(rows.data or []) == 1

        import redis as redis_lib

        redis_lib.from_url(settings.redis_url, decode_responses=True).delete(
            f"whatsapp:msg_seen:{msg_id}"
        )
