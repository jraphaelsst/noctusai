"""Tests for the WhatsApp inbound webhook — contract §3 item 19.

Mounts the SEED router verbatim (`create_whatsapp_webhook_router`) — no
second WAHA webhook verifier, no second dedup. Two test surfaces:

1. Through THIS PRODUCT's full app (`client` fixture) — proves the
   wiring (`on_message=handle_inbound`, group-filter drop, DB-unique
   dedup backstop) end to end. This product's `WhatsAppSettings` is
   constructed ONCE at `app.main` import time from
   `settings.community_waha_webhook_hmac_secret` (empty by default, the
   documented early-dev bypass — same posture as every other webhook
   secret in this product) — so the HMAC-required path is not
   reachable through the shared `client` fixture without mutating
   process-wide settings after other tests have already triggered the
   import.
2. A THROWAWAY app built directly from the SAME seed factory this
   product's router consumes (`create_whatsapp_webhook_router`), with a
   real secret configured — pins "HMAC required (secret always set in
   prod) -> missing/mismatch 401" (contract §3 item 19) against the
   actual seed behavior this product inherits, without fighting Python's
   module-import caching of `app.main`.
"""
import hashlib
import hmac
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.integrations.whatsapp import (
    InMemoryWebhookDedup,
    WhatsAppSettings,
    create_whatsapp_webhook_router,
)

from tests.conftest import ORG_UUID, seed_public_license

GRUPO_ID = "11111111-1111-1111-1111-111111111111"
CHAT_ID = "5511999990000@g.us"


def _group_message_payload(**over) -> dict:
    base = {
        "event": "message",
        "session": "default",
        "payload": {
            "id": "wamid-1",
            "chatId": CHAT_ID,
            "body": "Oi pessoal",
            "participant": "5511974693365@c.us",
        },
    }
    base.update(over)
    return base


class TestWiringThroughTheApp:
    def test_dm_message_is_ignored_no_group_row(self, client):
        seed_public_license(client)
        payload = _group_message_payload(payload={
            "id": "wamid-dm", "chatId": "5511974693365@c.us", "body": "oi",
        })
        resp = client.raw().post("/api/webhooks/whatsapp", json=payload)
        assert resp.status_code == 200
        rows = client.mock_supabase.table("grupo_mensagens").select("*").execute().data
        assert rows == []

    def test_unknown_group_is_accepted_but_dropped(self, client):
        seed_public_license(client)
        client.mock_supabase.set_table_data("grupos", [])
        resp = client.raw().post("/api/webhooks/whatsapp", json=_group_message_payload())
        assert resp.status_code == 200
        rows = client.mock_supabase.table("grupo_mensagens").select("*").execute().data
        assert rows == []

    def test_known_group_message_is_stored(self, client):
        seed_public_license(client)
        client.mock_supabase.set_table_data("grupos", [{
            "id": GRUPO_ID, "org_id": ORG_UUID, "chat_id": CHAT_ID, "ativo": True,
        }])
        client.mock_supabase.set_table_data("grupo_membros", [])
        # Unique provider_message_id — the seed's `InMemoryWebhookDedup` is
        # a process-lifetime singleton baked at `app.main` import time
        # (shared across every test in this session, not reset per test),
        # so reusing the module default id here would collide with
        # `TestUnknownEventAndDuplicate`'s own dedup assertions.
        payload = _group_message_payload(payload={
            "id": "wamid-known-group", "chatId": CHAT_ID, "body": "Oi pessoal",
            "participant": "5511974693365@c.us",
        })
        resp = client.raw().post("/api/webhooks/whatsapp", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        rows = client.mock_supabase.table("grupo_mensagens").select("*").execute().data
        assert len(rows) == 1
        assert rows[0]["grupo_id"] == GRUPO_ID


class TestHmacRequired:
    """Pins the seed's HMAC contract directly — see the module docstring."""

    def _build_app(self, *, secret: str | None):
        captured = []

        async def _on_message(inbound) -> None:
            captured.append(inbound)

        router = create_whatsapp_webhook_router(
            settings=WhatsAppSettings(base_url="http://waha.invalid", webhook_hmac_secret=secret),
            on_message=_on_message,
            dedup=InMemoryWebhookDedup(),
        )
        app = FastAPI()
        app.include_router(router, prefix="/webhook")
        return TestClient(app), captured

    def test_missing_signature_401(self):
        tc, captured = self._build_app(secret="s3cret")
        resp = tc.post("/webhook", json=_group_message_payload())
        assert resp.status_code == 401
        assert captured == []

    def test_wrong_signature_401(self):
        tc, captured = self._build_app(secret="s3cret")
        resp = tc.post(
            "/webhook", json=_group_message_payload(),
            headers={"X-Webhook-Hmac-SHA256": "0" * 64},
        )
        assert resp.status_code == 401
        assert captured == []

    def test_valid_signature_200(self):
        tc, captured = self._build_app(secret="s3cret")
        body = json.dumps(_group_message_payload()).encode()
        signature = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        resp = tc.post(
            "/webhook", content=body,
            headers={
                "X-Webhook-Hmac-SHA256": signature,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200
        assert len(captured) == 1


class TestUnknownEventAndDuplicate:
    def test_unsupported_event_type_ignored_200(self, client):
        seed_public_license(client)
        payload = _group_message_payload(event="session.status")
        resp = client.raw().post("/api/webhooks/whatsapp", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_duplicate_provider_message_id_returns_duplicate_200(self, client):
        seed_public_license(client)
        client.mock_supabase.set_table_data("grupos", [{
            "id": GRUPO_ID, "org_id": ORG_UUID, "chat_id": CHAT_ID, "ativo": True,
        }])
        client.mock_supabase.set_table_data("grupo_membros", [])
        payload = _group_message_payload(payload={
            "id": "wamid-dedup-test", "chatId": CHAT_ID, "body": "Oi pessoal",
            "participant": "5511974693365@c.us",
        })
        first = client.raw().post("/api/webhooks/whatsapp", json=payload)
        second = client.raw().post("/api/webhooks/whatsapp", json=payload)
        assert first.status_code == 200
        assert first.json()["status"] == "accepted"
        assert second.status_code == 200
        assert second.json()["status"] == "duplicate"
        rows = client.mock_supabase.table("grupo_mensagens").select("*").execute().data
        assert len(rows) == 1
