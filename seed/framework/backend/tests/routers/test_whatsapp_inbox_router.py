"""Tests for `noctusai_seed.whatsapp_inbox_router.create_whatsapp_inbox_router`.

Mounted TOGETHER with the seed connections router, because the headline
contract is the round trip: the webhook URL the connections router MINTS per
connection is exactly the path the inbox router RECEIVES on. Drives both
against `FakeWahaClient` (DI seam, no monkeypatching) and the inbox
`FakeWhatsAppChatStore`. Auth-boundary tests assert strict `== 401`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from urllib.parse import urlparse
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from noctusai_lib.integrations.whatsapp import FakeWahaClient
from noctusai_lib.integrations.whatsapp.connection_store import build_whatsapp_connection_store
from noctusai_lib.integrations.whatsapp.inbox import (
    build_inbox_realtime,
    build_whatsapp_chat_store,
)
from noctusai_lib.integrations.whatsapp.lid_auth import InMemoryLidPhoneCache
from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_seed.whatsapp_connections_router import create_whatsapp_connections_router
from noctusai_seed.whatsapp_inbox_router import create_whatsapp_inbox_router

ORG_A = str(uuid.uuid4())
ORG_B = str(uuid.uuid4())
USER = str(uuid.uuid4())
SECRET = "wh-secret"
CHAT = "5511999990001@c.us"


# ─── minimal PostgREST double for the CONNECTION store (state-coherent) ────
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows, self._filters, self._op, self._payload = rows, {}, None, None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def _matches(self, row):
        return all(row.get(k) == v for k, v in self._filters.items())

    def execute(self):
        if self._op == "select":
            return _Resp([dict(r) for r in self._rows if self._matches(r)])
        if self._op == "insert":
            row = dict(self._payload)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", "2026-10-26T00:00:00+00:00")
            row.setdefault("updated_at", "2026-10-26T00:00:00+00:00")
            self._rows.append(row)
            return _Resp([row])
        if self._op == "update":
            hit = [r for r in self._rows if self._matches(r)]
            for row in hit:
                row.update(self._payload)
            return _Resp([dict(r) for r in hit])
        removed = [r for r in self._rows if self._matches(r)]
        self._rows[:] = [r for r in self._rows if not self._matches(r)]
        return _Resp(removed)


class _FakeSupabase:
    def __init__(self):
        self._tables: dict[str, list] = {}

    def schema(self, _name):
        outer = self

        class _H:
            def table(self, name):
                return _Query(outer._tables.setdefault(name, []))

        return _H()


def _auth(org=ORG_A, *, raise_401=False):
    def _dep():
        if raise_401:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        user = MagicMock()
        user.id = USER
        return (user, "tok", org)

    return _dep


class _Harness:
    def __init__(self, *, hmac_secret=None, org=ORG_A, raise_401=False, mirror_read=False, realtime=True,
                 with_lid_cache=False, on_purge=None, audit_sink=None):
        self.conn_store = build_whatsapp_connection_store(
            _FakeSupabase(), encryption_key=generate_key().decode(), schema="monica"
        )
        self.chat_store = build_whatsapp_chat_store(None, schema="monica", allow_fake=True)
        self.waha = FakeWahaClient(session="default")
        self.new_chats: list = []
        self.messages: list = []
        self.realtime = build_inbox_realtime(allow_in_process=True) if realtime else None
        self.lid_cache = InMemoryLidPhoneCache() if with_lid_cache else None

        def waha_factory(*, base_url=None, api_key=None, session="default"):  # noqa: ARG001
            return self.waha

        async def on_new_chat(org_id, connection_id, chat):
            self.new_chats.append((org_id, connection_id, chat))

        async def on_message(org_id, connection_id, chat, message):
            self.messages.append((chat.chat_id, message.from_me, message.body))

        app = FastAPI()
        app.include_router(create_whatsapp_connections_router(
            MagicMock(), MagicMock(), store_factory=lambda: self.conn_store,
            get_current_user_org=_auth(org, raise_401=raise_401), waha_base_url="https://waha.example.com",
            resolve_webhook_base_url=lambda: "https://monica.example.com", waha_client_factory=waha_factory,
            chat_store_factory=lambda: self.chat_store, on_purge=on_purge, audit_product_slug="monica",
        ))
        if audit_sink is not None:
            app.state.audit_sink, app.state.audit_enabled = audit_sink, True
        app.include_router(create_whatsapp_inbox_router(
            chat_store_factory=lambda: self.chat_store, connection_store_factory=lambda: self.conn_store,
            get_current_user_org=_auth(org, raise_401=raise_401), waha_client_factory=waha_factory,
            on_new_chat=on_new_chat, on_message=on_message, realtime=self.realtime, lid_cache=self.lid_cache,
            webhook_hmac_secret=hmac_secret, mirror_read_to_whatsapp=mirror_read,
        ))
        self.client = TestClient(app)

    def create_connection(self, **extra) -> tuple[str, str]:
        """Create via the seed connections router; returns (connection_id, minted webhook PATH)."""
        resp = self.client.post("/api/whatsapp/connections", json={"label": "Mônica", "api_key": "k", **extra})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        return body["id"], urlparse(body["webhook_url"]).path

    def post_event(self, path, body, *, secret=None):
        raw = json.dumps(body).encode()
        headers = {"content-type": "application/json"}
        if secret:
            headers["X-Webhook-Hmac-SHA256"] = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return self.client.post(path, content=raw, headers=headers)


def _msg(mid="m1", *, chat=CHAT, body="oi", from_me=False, event="message", ts=None):
    return {"event": event, "session": "default", "payload": {
        "id": mid, "timestamp": ts or int(time.time()), "from": chat if not from_me else "5511000000000@c.us",
        "to": "5511000000000@c.us" if not from_me else chat, "fromMe": from_me, "body": body,
        "hasMedia": False, "_data": {"notifyName": "Paciente"},
    }}


# ─── the headline contract ──────────────────────────────────────────────────


def test_webhook_path_matches_minted_url():
    """The URL the connections router registers on WAHA IS the inbox webhook route."""
    h = _Harness()
    conn_id, path = h.create_connection()
    assert path.startswith("/api/whatsapp/webhook/")
    assert h.waha.webhook_config["url"].endswith(path)
    resp = h.post_event(path, _msg())
    assert resp.status_code == 200 and resp.json() == {"status": "message"}
    chats = h.client.get(f"/api/whatsapp/connections/{conn_id}/chats").json()
    assert [c["chat_id"] for c in chats["items"]] == [CHAT]
    assert chats["items"][0]["unread_count"] == 1 and chats["next_cursor"] is None
    msgs = h.client.get(f"/api/whatsapp/connections/{conn_id}/chats/{CHAT}/messages").json()
    assert [m["body"] for m in msgs["items"]] == ["oi"] and msgs["has_more"] is False


def test_webhook_fires_on_new_chat_once_for_replay_and_message_pair():
    h = _Harness()
    _conn_id, path = h.create_connection()
    for event in ("message", "message.any", "message", "message.any"):
        assert h.post_event(path, _msg(event=event)).status_code == 200
    assert len(h.new_chats) == 1
    assert h.new_chats[0][2].chat_id == CHAT


def test_unknown_token_is_a_generic_404():
    h = _Harness()
    assert h.post_event("/api/whatsapp/webhook/nope", _msg()).status_code == 404


def test_webhook_rejects_missing_and_bad_signature_with_401_when_secret_set():
    h = _Harness(hmac_secret=SECRET)
    _id, path = h.create_connection()
    assert h.post_event(path, _msg()).status_code == 401  # no signature
    raw = json.dumps(_msg()).encode()
    bad = h.client.post(path, content=raw, headers={"X-Webhook-Hmac-SHA256": "00" * 32})
    assert bad.status_code == 401
    assert h.post_event(path, _msg(), secret=SECRET).status_code == 200


def test_webhook_invalid_json_is_acknowledged_not_retried():
    h = _Harness()
    _id, path = h.create_connection()
    resp = h.client.post(path, content=b"not json", headers={"content-type": "application/json"})
    assert resp.status_code == 200 and resp.json() == {"status": "ignored"}


# ─── auth boundary: strict 401 ──────────────────────────────────────────────


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/whatsapp/connections/{c}/chats", None),
    ("get", "/api/whatsapp/connections/{c}/chats/x@c.us/messages", None),
    ("post", "/api/whatsapp/connections/{c}/chats/x@c.us/messages", {"text": "oi"}),
    ("post", "/api/whatsapp/connections/{c}/chats/x@c.us/read", None),
    ("post", "/api/whatsapp/connections/{c}/backfill", None),
    ("get", "/api/whatsapp/connections/{c}/events", None),
])
def test_authenticated_routes_return_strict_401_without_auth(method, path, body):
    h = _Harness(raise_401=True)
    resp = getattr(h.client, method)(path.format(c=uuid.uuid4()), **({"json": body} if body else {}))
    assert resp.status_code == 401


# ─── org scoping ────────────────────────────────────────────────────────────


def test_other_orgs_connection_is_404_on_every_route():
    owner = _Harness()
    conn_id, path = owner.create_connection()
    owner.post_event(path, _msg())
    intruder_app = FastAPI()
    intruder_app.include_router(create_whatsapp_inbox_router(
        chat_store_factory=lambda: owner.chat_store, connection_store_factory=lambda: owner.conn_store,
        get_current_user_org=_auth(ORG_B), realtime=owner.realtime,
    ))
    client = TestClient(intruder_app)
    base = f"/api/whatsapp/connections/{conn_id}"
    assert client.get(f"{base}/chats").status_code == 404
    assert client.get(f"{base}/chats/{CHAT}/messages").status_code == 404
    assert client.post(f"{base}/chats/{CHAT}/messages", json={"text": "x"}).status_code == 404
    assert client.post(f"{base}/chats/{CHAT}/read").status_code == 404
    assert client.post(f"{base}/backfill").status_code == 404
    assert client.get(f"{base}/events").status_code == 404


def test_on_message_fires_for_inbound_webhook_and_outbound_send_but_not_for_duplicates():
    h = _Harness()
    conn_id, path = h.create_connection()
    for event in ("message", "message.any"):  # the pair is ONE stored message
        h.post_event(path, _msg(event=event))
    h.client.post(f"/api/whatsapp/connections/{conn_id}/chats/{CHAT}/messages", json={"text": "Olá!"})
    h.post_event(path, _msg("fake-msg-1", from_me=True, body="Olá!", event="message.any"))  # echo = duplicate
    assert h.messages == [(CHAT, False, "oi"), (CHAT, True, "Olá!")]


# ─── send ───────────────────────────────────────────────────────────────────


def test_send_persists_from_me_and_the_echo_does_not_duplicate():
    h = _Harness()
    conn_id, path = h.create_connection()
    h.post_event(path, _msg())
    resp = h.client.post(f"/api/whatsapp/connections/{conn_id}/chats/{CHAT}/messages", json={"text": "Olá!"})
    assert resp.status_code == 201
    sent = resp.json()
    assert sent["from_me"] is True and sent["body"] == "Olá!" and sent["id"] == "fake-msg-1"
    assert h.waha.sent_messages[0]["chatId"] == CHAT
    # WAHA echoes our own send as message.any with the same id -> deduped by UNIQUE
    echo = h.post_event(path, _msg("fake-msg-1", from_me=True, body="Olá!", event="message.any"))
    assert echo.json() == {"status": "duplicate"}
    msgs = h.client.get(f"/api/whatsapp/connections/{conn_id}/chats/{CHAT}/messages").json()["items"]
    assert [m["body"] for m in msgs] == ["oi", "Olá!"]
    chat = h.client.get(f"/api/whatsapp/connections/{conn_id}/chats").json()["items"][0]
    assert chat["last_message_preview"] == "Olá!" and chat["last_message_from_me"] is True
    # a later ack lands on the persisted message
    h.post_event(path, {"event": "message.ack", "payload": {"id": "fake-msg-1", "ack": 3}})
    msgs = h.client.get(f"/api/whatsapp/connections/{conn_id}/chats/{CHAT}/messages").json()["items"]
    assert msgs[-1]["ack"] == 3


def test_send_validates_and_404s_unknown_chat():
    h = _Harness()
    conn_id, path = h.create_connection()
    base = f"/api/whatsapp/connections/{conn_id}/chats/{CHAT}/messages"
    assert h.client.post(base, json={"text": "oi"}).status_code == 404  # chat does not exist yet
    h.post_event(path, _msg())
    assert h.client.post(base, json={"text": ""}).status_code == 422
    assert h.client.post(base, json={"text": "x" * 5000}).status_code == 422
    assert h.client.post(base, json={"text": "x", "extra": 1}).status_code == 422


def test_send_waha_failure_is_502_and_persists_nothing():
    h = _Harness()
    conn_id, path = h.create_connection()
    h.post_event(path, _msg())

    async def boom(chat_id, text):
        raise RuntimeError("waha down")

    h.waha.send_text = boom
    resp = h.client.post(f"/api/whatsapp/connections/{conn_id}/chats/{CHAT}/messages", json={"text": "x"})
    assert resp.status_code == 502
    msgs = h.client.get(f"/api/whatsapp/connections/{conn_id}/chats/{CHAT}/messages").json()["items"]
    assert len(msgs) == 1


def test_send_never_falls_back_to_the_fake_client_when_base_url_is_blank():
    h = _Harness()
    record = h.conn_store.create_connection(
        org_id=uuid.UUID(ORG_A), user_id=uuid.UUID(USER), label="sem url", base_url="", api_key="k",
        webhook_token="t2",
    )
    h.chat_store.ensure_chat(
        org_id=uuid.UUID(ORG_A), connection_id=record.id, chat_id=CHAT, name="P", phone=None,
        is_group=False, origin="inbound",
    )
    resp = h.client.post(f"/api/whatsapp/connections/{record.id}/chats/{CHAT}/messages", json={"text": "x"})
    assert resp.status_code == 503 and h.waha.sent_messages == []


def test_send_to_lid_binds_the_resolved_phone():
    h = _Harness(with_lid_cache=True)
    conn_id, path = h.create_connection()
    h.post_event(path, _msg(chat="99999@lid"))
    original = h.waha.send_text

    async def send(chat_id, text):
        result = await original(chat_id, text)
        result["_data"] = {"id": {"remote": "5511999990001@c.us"}}
        return result

    h.waha.send_text = send
    assert h.client.post(
        f"/api/whatsapp/connections/{conn_id}/chats/99999@lid/messages", json={"text": "oi"}
    ).status_code == 201
    assert h.lid_cache.get_phone_for_lid("99999@lid") == "5511999990001"


# ─── read / backfill / events ───────────────────────────────────────────────


def test_mark_read_204_zeroes_badge_and_unknown_chat_404():
    h = _Harness()
    conn_id, path = h.create_connection()
    h.post_event(path, _msg())
    base = f"/api/whatsapp/connections/{conn_id}/chats"
    assert h.client.post(f"{base}/{CHAT}/read").status_code == 204
    assert h.client.get(base).json()["items"][0]["unread_count"] == 0
    assert h.client.post(f"{base}/ghost@c.us/read").status_code == 404
    assert h.waha.seen_calls == []  # mirroring to the phone is OFF by default


def test_mark_read_mirrors_send_seen_only_when_opted_in():
    h = _Harness(mirror_read=True)
    conn_id, path = h.create_connection()
    h.post_event(path, _msg())
    assert h.client.post(f"/api/whatsapp/connections/{conn_id}/chats/{CHAT}/read").status_code == 204
    assert len(h.waha.seen_calls) == 1


def test_backfill_returns_202_and_imports_history():
    h = _Harness()
    conn_id, _path = h.create_connection()
    h.waha.fake_chat_list = [{"id": {"_serialized": CHAT}, "name": "Paciente"}]
    h.waha.fake_chat_messages[CHAT] = [
        {"id": {"_serialized": "h1"}, "body": "histórico", "from": CHAT, "fromMe": False, "timestamp": int(time.time()) - 3600}
    ]
    resp = h.client.post(f"/api/whatsapp/connections/{conn_id}/backfill")
    assert resp.status_code == 202 and resp.json() == {"status": "started"}
    chats = h.client.get(f"/api/whatsapp/connections/{conn_id}/chats").json()["items"]
    assert [c["last_message_preview"] for c in chats] == ["histórico"]
    assert h.new_chats == []  # history is never a "new chat"


def test_events_route_exists_only_with_a_realtime_bus():
    with_bus = _Harness()
    without = _Harness(realtime=False)
    sse = lambda h: [r for r in h.client.app.routes if getattr(r, "path", "").endswith("/events")]  # noqa: E731
    assert sse(with_bus) and not sse(without)


def test_bad_cursor_is_422():
    h = _Harness()
    conn_id, _ = h.create_connection()
    assert h.client.get(f"/api/whatsapp/connections/{conn_id}/chats?cursor=garbage").status_code == 422


# ─── per-app switch ─────────────────────────────────────────────────────────


def test_disabled_connection_webhook_stores_nothing_and_fires_no_hooks():
    h = _Harness()
    conn_id, path = h.create_connection()
    base = f"/api/whatsapp/connections/{conn_id}"
    resp = h.client.put(f"{base}/enabled", json={"enabled": False})
    assert resp.status_code == 200 and resp.json()["app_enabled"] is False
    resp = h.post_event(path, _msg())
    assert resp.status_code == 200 and resp.json() == {"status": "disabled"}  # 200: WAHA must not retry
    assert h.new_chats == [] and h.messages == []
    assert h.client.get(f"{base}/chats").json()["items"] == []
    # switching back on resumes ingestion
    assert h.client.put(f"{base}/enabled", json={"enabled": True}).json()["app_enabled"] is True
    assert h.post_event(path, _msg("m2")).json() == {"status": "message"}
    assert len(h.new_chats) == 1


def test_send_is_refused_409_app_disabled_while_off():
    h = _Harness()
    conn_id, path = h.create_connection()
    h.post_event(path, _msg())
    base = f"/api/whatsapp/connections/{conn_id}"
    h.client.put(f"{base}/enabled", json={"enabled": False})
    sent_before = len(h.waha.sent) if hasattr(h.waha, "sent") else None
    resp = h.client.post(f"{base}/chats/{CHAT}/messages", json={"text": "oi"})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "app_disabled"
    if sent_before is not None:
        assert len(h.waha.sent) == sent_before


def test_enabled_route_is_org_scoped_and_strict_401():
    h = _Harness()
    conn_id, _path = h.create_connection()
    assert _Harness(raise_401=True).client.put(
        f"/api/whatsapp/connections/{conn_id}/enabled", json={"enabled": False}
    ).status_code == 401
    intruder = FastAPI()
    intruder.include_router(create_whatsapp_connections_router(
        MagicMock(), MagicMock(), store_factory=lambda: h.conn_store, get_current_user_org=_auth(ORG_B),
        waha_base_url="https://waha.example.com", resolve_webhook_base_url=lambda: "https://monica.example.com",
    ))
    resp = TestClient(intruder).put(f"/api/whatsapp/connections/{conn_id}/enabled", json={"enabled": False})
    assert resp.status_code == 404
    assert h.conn_store.get_connection(connection_id=uuid.UUID(conn_id), org_id=uuid.UUID(ORG_A)).app_enabled is True


# ─── borrowed session ───────────────────────────────────────────────────────


@pytest.mark.parametrize("method,suffix,body", [
    ("post", "start", None), ("post", "restart", None), ("post", "logout", None), ("post", "recover", None),
    ("get", "qr", None), ("post", "backfill", None),
    ("post", "webhook", {"url": "https://monica.example.com/api/whatsapp/webhook/x", "events": ["message"]}),
])
def test_borrower_session_controls_are_409_session_borrowed(method, suffix, body):
    h = _Harness()
    conn_id, _path = h.create_connection(session_role="borrower")
    # a borrower registers ITS OWN webhook but never starts/pairs the shared session
    assert h.waha.start_count == 0 and h.waha.webhook_config is not None
    resp = getattr(h.client, method)(f"/api/whatsapp/connections/{conn_id}/{suffix}", **({"json": body} if body else {}))
    assert resp.status_code == 409, suffix
    assert resp.json()["detail"]["code"] == "session_borrowed"


def test_borrower_is_exposed_and_still_ingests_and_owner_controls_still_work():
    h = _Harness()
    conn_id, path = h.create_connection(session_role="borrower")
    listed = h.client.get("/api/whatsapp/connections").json()
    assert listed[0]["session_role"] == "borrower" and listed[0]["app_enabled"] is True
    assert h.post_event(path, _msg()).json() == {"status": "message"}
    h2 = _Harness()  # default role: owner
    oid, _p = h2.create_connection()
    assert h2.client.post(f"/api/whatsapp/connections/{oid}/restart").status_code == 200


# ─── purge ──────────────────────────────────────────────────────────────────


def test_purge_is_refused_while_the_app_is_on():
    h = _Harness()
    conn_id, path = h.create_connection()
    h.post_event(path, _msg())
    resp = h.client.post(f"/api/whatsapp/connections/{conn_id}/purge", json={"confirm": "Mônica"})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "app_enabled"
    assert len(h.client.get(f"/api/whatsapp/connections/{conn_id}/chats").json()["items"]) == 1


def test_purge_requires_the_typed_label():
    h = _Harness()
    conn_id, _path = h.create_connection()
    h.client.put(f"/api/whatsapp/connections/{conn_id}/enabled", json={"enabled": False})
    resp = h.client.post(f"/api/whatsapp/connections/{conn_id}/purge", json={"confirm": "wrong"})
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "confirm_mismatch"


def test_purge_runs_the_seam_first_then_deletes_chats_and_audits_counts_only():
    order: list[str] = []
    audited: list = []

    class _Sink:
        async def record(self, entry):
            audited.append(entry)

    async def on_purge(org_id, connection_id):
        # the chats are still there when the product erases its derived data
        order.append(f"seam:{len(h.chat_store.list_connection_chat_ids(org_id=org_id, connection_id=connection_id))}")
        return {"leads_deleted": 3, "leads_detached": 1}

    h = _Harness(on_purge=on_purge, audit_sink=_Sink())
    conn_id, path = h.create_connection()
    h.post_event(path, _msg("m1"))
    h.post_event(path, _msg("m2", chat="5511999990002@c.us"))
    base = f"/api/whatsapp/connections/{conn_id}"
    h.client.put(f"{base}/enabled", json={"enabled": False})
    resp = h.client.post(f"{base}/purge", json={"confirm": "Mônica"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "connection_id": conn_id, "chats_deleted": 2, "messages_deleted": 2,
        "extra": {"leads_deleted": 3, "leads_detached": 1},
    }
    assert order == ["seam:2"]
    assert h.chat_store.list_connection_chat_ids(org_id=uuid.UUID(ORG_A), connection_id=uuid.UUID(conn_id)) == []
    # the line itself survives the purge (it is not a delete)
    assert h.client.get("/api/whatsapp/connections").json()[0]["id"] == conn_id
    assert len(audited) == 1
    params = audited[0].path_params
    assert params["chats_deleted"] == 2 and params["leads_deleted"] == 3
    assert "Mônica" not in repr(audited[0]) and CHAT not in repr(audited[0])


def test_purge_is_org_scoped_and_strict_401():
    h = _Harness()
    conn_id, _path = h.create_connection()
    h.client.put(f"/api/whatsapp/connections/{conn_id}/enabled", json={"enabled": False})
    assert _Harness(raise_401=True).client.post(
        f"/api/whatsapp/connections/{conn_id}/purge", json={"confirm": "Mônica"}
    ).status_code == 401
    app = FastAPI()
    app.include_router(create_whatsapp_connections_router(
        MagicMock(), MagicMock(), store_factory=lambda: h.conn_store, get_current_user_org=_auth(ORG_B),
        waha_base_url="https://waha.example.com", resolve_webhook_base_url=lambda: "https://monica.example.com",
        chat_store_factory=lambda: h.chat_store,
    ))
    assert TestClient(app).post(
        f"/api/whatsapp/connections/{conn_id}/purge", json={"confirm": "Mônica"}
    ).status_code == 404
