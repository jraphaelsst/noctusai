"""The Assistant's shadow-line guarantees: HMAC required, no write/read-history routes, the pre-store input contract,
dedup, and that the intake row + its event are ONE transaction (one RPC; the SQL function writes both)."""
import asyncio
import hashlib
import hmac as _hmac
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.integrations.whatsapp.inbox import ingest_waha_event
from noctusai_lib.testing.migrations import migration_sql
from noctusai_seed.whatsapp_inbox_router import WebhookHmacRequired, create_whatsapp_inbox_router

from app.services.intake import IdentityKeyNotConfigured, IntakeChatStore, chat_ref

SECRET = "test-webhook-secret"
ROOT = Path(__file__).resolve().parents[1]


# ── fakes ───────────────────────────────────────────────────────────────────────────────────────
class _FakeRpcClient:
    """Emulates `append_intake`'s dedup contract and records every RPC (one call == one transaction)."""

    def __init__(self):
        self.calls, self._seen = [], set()

    def rpc(self, name, params):
        self.calls.append((name, params))
        key = (params["p_connection_id"], params["p_waha_message_id"])
        fresh = key not in self._seen
        self._seen.add(key)
        data = [{"id": str(uuid4()), "outcome": "pending"}] if fresh else []
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))


_RECORD = SimpleNamespace(org_id=uuid4(), id=uuid4(), app_enabled=True)


def _record():
    return _RECORD


def _event(message_id="m1", chat="5511988887777@c.us", from_me=False, body="oi, posso marcar?", source="app"):
    return {
        "event": "message",
        "payload": {
            "id": message_id, "from": chat, "fromMe": from_me, "body": body, "timestamp": 1_800_000_000,
            "source": source, "hasMedia": False, "_data": {"notifyName": "X"},
        },
    }


def _ingest(body, store, should_store=None):
    from app.routers.whatsapp_router import build_should_store

    return asyncio.run(
        ingest_waha_event(
            body, connection=_record(), chat_store=store, should_store=should_store or build_should_store()
        )
    )


def _store():
    client = _FakeRpcClient()
    return client, IntakeChatStore(lambda: client, lambda: "test-identity-key")


# ── HMAC required (strict 401) ──────────────────────────────────────────────────────────────────
def _sign(body: bytes) -> dict:
    return {"X-Webhook-Hmac": _hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest(), "X-Webhook-Hmac-Algorithm": "sha512"}


def test_unsigned_webhook_is_401(client):
    resp = client.post("/api/whatsapp/webhook/anything", content=b"{}")
    assert resp.status_code == 401


def test_bad_signature_is_401(client):
    resp = client.post(
        "/api/whatsapp/webhook/anything", content=b"{}",
        headers={"X-Webhook-Hmac": "00" * 64, "X-Webhook-Hmac-Algorithm": "sha512"},
    )
    assert resp.status_code == 401


def test_valid_signature_reaches_the_token_check(client):
    body = b"{}"
    resp = client.post("/api/whatsapp/webhook/unknown-token", content=body, headers=_sign(body))
    assert resp.status_code != 401  # signature accepted; the unknown token is the generic 404 (or the store's 503)


def _bare_inbox(secret, **kw):
    app = FastAPI()
    app.include_router(
        create_whatsapp_inbox_router(
            chat_store_factory=lambda: None, connection_store_factory=lambda: None,
            get_current_user_org=lambda: None, webhook_hmac_secret=secret, require_webhook_hmac=True,
            webhook_only=True, **kw,
        )
    )
    return app


def test_no_secret_rejects_every_webhook_with_401():
    resp = TestClient(_bare_inbox(None)).post("/api/whatsapp/webhook/t", content=b"{}")
    assert resp.status_code == 401


def test_deploy_without_secret_refuses_to_boot(monkeypatch):
    monkeypatch.setattr("noctusai_seed.whatsapp_inbox_router.is_deploy_context", lambda: True)
    with pytest.raises(WebhookHmacRequired):
        _bare_inbox(None)
    _bare_inbox("secret")  # with a secret it builds


# ── the inbox routes exist (owner decision 2026-11-12) and are ALL admin-gated ──────────────────
def test_the_inbox_routes_are_mounted_next_to_the_connections_and_the_webhook(client):
    from app.main import app

    paths = {(m, r.path) for r in app.routes for m in (getattr(r, "methods", None) or ())}
    base = "/api/whatsapp/connections/{connection_id}"
    for route in (
        ("GET", f"{base}/chats"), ("GET", f"{base}/chats/{{chat_id:path}}/messages"),
        ("POST", f"{base}/chats/{{chat_id:path}}/messages"), ("POST", f"{base}/chats/{{chat_id:path}}/read"),
        ("POST", f"{base}/backfill"), ("POST", "/api/whatsapp/webhook/{token}"),
    ):
        assert route in paths, route
    assert ("POST", f"{base}/start") in paths  # session lifecycle is not a send


# ── the pre-store input contract ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "event, statuses",
    [
        # from_me / status broadcasts never survive the seed parser ("ignored"); the predicate is the second wall.
        (_event(from_me=True), {"ignored", "skipped"}),
        (_event(chat="120363000000000000@g.us"), {"skipped"}),
        (_event(chat="status@broadcast"), {"ignored", "skipped"}),
        (_event(chat="5511999990000@c.us"), {"skipped"}),
        (_event(source="api"), {"skipped"}),
    ],
)
def test_should_store_skips_before_anything_is_written(event, statuses):
    client, store = _store()
    result = _ingest(event, store)
    assert result.status in statuses
    assert client.calls == []  # nothing reached the intake


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"from_me": True}, "from_me"),
        ({"chat": "120363000000000000@g.us"}, "group"),
        ({"chat": "status@broadcast"}, "broadcast"),
        ({"chat": "5511999990000@c.us"}, "excluded"),
        ({"source": "api"}, "api_sourced"),
    ],
)
def test_the_predicate_names_the_reason(kwargs, reason):
    from noctusai_lib.integrations.whatsapp.inbox.ingest import ChatIdentity
    from noctusai_lib.integrations.whatsapp.inbox.types import InboxMessage
    from app.routers.whatsapp_router import build_should_store

    chat = kwargs.get("chat", "5511988887777@c.us")
    msg = InboxMessage(
        id="x", chat_id=chat, from_me=kwargs.get("from_me", False), body="oi", type="chat", media_url=None,
        ack=None, timestamp="2026-11-10T10:00:00+00:00", sender_name=None, source=kwargs.get("source"),
    )
    identity = ChatIdentity(chat, None if chat.endswith("@g.us") else chat.split("@")[0], None, chat.endswith("@g.us"))
    assert build_should_store()(msg, identity) == reason


def test_inbound_one_to_one_text_is_taken_in_once_and_deduplicated():
    client, store = _store()
    assert _ingest(_event("m1"), store).status == "message"
    assert _ingest(_event("m1"), store).status == "duplicate"
    assert [c[0] for c in client.calls] == ["append_intake", "append_intake"]


def test_intake_carries_a_keyed_reference_never_the_phone():
    client, store = _store()
    _ingest(_event("m2", chat="5511988887777@c.us"), store)
    params = client.calls[0][1]
    assert "5511988887777" not in json.dumps(params)
    assert params["p_chat_ref"] == chat_ref("test-identity-key", "5511988887777@c.us")
    assert chat_ref("other-key", "5511988887777@c.us") != params["p_chat_ref"]


def test_identity_key_unset_refuses_instead_of_storing():
    with pytest.raises(IdentityKeyNotConfigured):
        chat_ref("", "5511988887777@c.us")


def test_a_failed_append_propagates_so_waha_retries():
    class _Boom:
        def rpc(self, *_a, **_k):
            raise RuntimeError("db down")

    store = IntakeChatStore(lambda: _Boom(), lambda: "k")
    with pytest.raises(RuntimeError):
        _ingest(_event("m3"), store)


# ── the intake row and its event are one transaction (migration 015) ────────────────────────────
def test_append_intake_writes_row_and_event_in_one_function():
    sql = migration_sql(ROOT, "intake")
    body = sql.split("FUNCTION assistant.append_intake(", 1)[1].split("$$;", 1)[0]
    assert "INSERT INTO assistant.intake_messages\n" in body and "INSERT INTO assistant.intake_messages_eventos" in body
    assert "ON CONFLICT (connection_id, waha_message_id) DO NOTHING" in body  # dedup
    for reason in ("not_paired", "before_pairing", "no_text"):
        assert reason in body


def test_set_intake_outcome_writes_change_and_event_in_one_function():
    sql = migration_sql(ROOT, "intake")
    body = sql.split("FUNCTION assistant.set_intake_outcome(", 1)[1].split("$$;", 1)[0]
    assert "UPDATE assistant.intake_messages" in body and "INSERT INTO assistant.intake_messages_eventos" in body


def test_every_table_is_tiered_service_only_and_writers_are_not_browser_callable():
    sql = migration_sql(ROOT, "intake")
    for table in ("whatsapp_connections", "intake_messages", "intake_messages_eventos"):
        assert f"COMMENT ON TABLE assistant.{table} IS 'tier:org';" in sql
        assert f"REVOKE ALL ON assistant.{table} FROM PUBLIC, anon, authenticated;" in sql
    for fn in ("append_intake", "set_intake_outcome"):
        assert f"REVOKE ALL ON FUNCTION assistant.{fn}(" in sql
    assert "'pending', 'classified', 'failed', 'skipped_budget', 'skipped_excluded', 'skipped'" in sql
    assert "retain_until timestamptz NOT NULL DEFAULT (now() + interval '90 days')" in sql
