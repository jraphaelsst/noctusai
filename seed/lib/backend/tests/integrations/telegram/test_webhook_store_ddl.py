"""401 strict, 409 clobber guard, line store (encrypted, org-scoped), events sink, DDL tiers."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_lib.integrations.telegram import (
    FakeTelegramClient, FakeTelegramLineEventSink, FakeTelegramLineStore, LineEventPersistenceError,
    SupabaseTelegramLineStore, TelegramLineConflictError, TelegramLineEvent, TelegramLineStoreError,
    WebhookEstrangeiroError, connect_webhook, ensure_webhook_ours, require_telegram_secret_token,
    telegram_tables_sql, verify_telegram_secret_token, webhook_estrangeiro_http_exception,
)
from noctusai_lib.integrations.telegram.ddl import TABLES
from noctusai_lib.integrations.telegram.events import make_telegram_line_event_sink

run = asyncio.run
SECRET = "s3cr3t_token-ABC"


def _app():
    app = FastAPI()

    @app.post("/hook")
    def hook(x_telegram_bot_api_secret_token: str | None = Header(default=None)):
        require_telegram_secret_token(x_telegram_bot_api_secret_token, SECRET)
        return {"ok": True}

    return app


def test_webhook_secret_strict_401():
    c = TestClient(_app())
    assert c.post("/hook").status_code == 401  # missing
    assert c.post("/hook", headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}).status_code == 401
    assert c.post("/hook", headers={"X-Telegram-Bot-Api-Secret-Token": ""}).status_code == 401
    assert c.post("/hook", headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}).status_code == 200


def test_verify_never_open_when_stored_secret_missing():
    assert verify_telegram_secret_token(SECRET, SECRET)
    assert not verify_telegram_secret_token(None, SECRET)
    assert not verify_telegram_secret_token("x", None)
    assert not verify_telegram_secret_token("", "")


def test_clobber_guard_409_on_foreign_webhook():
    f = FakeTelegramClient()
    run(f.set_webhook("https://other-app.example/hook", secret_token="abc"))
    with pytest.raises(WebhookEstrangeiroError) as ei:
        run(connect_webhook(f, "https://ours.example/hook", "ours-secret"))
    assert ei.value.status == 409 and ei.value.code == "webhook_estrangeiro"
    assert f.webhook.url == "https://other-app.example/hook"  # untouched
    exc = webhook_estrangeiro_http_exception(ei.value)
    assert exc.status_code == 409 and exc.detail == {"code": "webhook_estrangeiro"}


def test_connect_webhook_sets_when_empty_or_already_ours_and_reads_back():
    f = FakeTelegramClient()
    info = run(connect_webhook(f, "https://ours.example/hook", "ours-secret"))
    assert info.url == "https://ours.example/hook" and f.webhook_secret == "ours-secret"
    run(connect_webhook(f, "https://ours.example/hook", "rotated-secret"))  # idempotent re-set
    assert f.webhook_secret == "rotated-secret"
    run(ensure_webhook_ours(f, "https://ours.example/hook"))


# ---------------- line store ----------------
def test_line_store_encrypts_scopes_by_org_and_enforces_unique_bot():
    key = generate_key()
    st = FakeTelegramLineStore([key])
    org, other, user = uuid4(), uuid4(), uuid4()
    tok = "111:AAHsecretsecretsecretsecretsecret1234"
    rec = st.create_line(org_id=org, created_by=user, label="L", bot_token=tok, bot_id=111, bot_username="b")
    assert rec.bot_token is None and rec.token_last4 == tok[-4:]
    assert tok not in repr(rec) and tok not in str(st.rows)  # encrypted at rest, never in repr
    assert st.get_line(line_id=rec.id, org_id=other) is None  # org scoping
    full = st.get_line(line_id=rec.id, org_id=org, decrypt=True)
    assert full.bot_token == tok and full.webhook_secret
    assert st.get_by_webhook_token(rec.webhook_token).id == rec.id
    assert st.get_by_webhook_token("nope") is None
    with pytest.raises(TelegramLineConflictError):
        st.create_line(org_id=other, created_by=user, label="L2", bot_token=tok, bot_id=111, bot_username="b")
    old_secret = full.webhook_secret
    st.rotate_token(line_id=rec.id, org_id=org, bot_token="111:NEWnewnewnewnewnewnewnewnewnew9999", bot_id=111, bot_username="b")
    new = st.get_line(line_id=rec.id, org_id=org, decrypt=True)
    assert new.bot_token.endswith("9999") and new.webhook_secret != old_secret
    assert st.set_status(line_id=rec.id, org_id=org, status="suspended").status == "suspended"
    with pytest.raises(ValueError):
        st.set_status(line_id=rec.id, org_id=org, status="bogus")
    assert not st.delete_line(line_id=rec.id, org_id=other) and st.delete_line(line_id=rec.id, org_id=org)


def test_line_store_wrong_key_is_loud_and_rotation_window_reads_old_rows():
    old, new = generate_key(), generate_key()
    st = FakeTelegramLineStore([old])
    org = uuid4()
    rec = st.create_line(org_id=org, created_by=uuid4(), label="L", bot_token="1:" + "A" * 40, bot_id=1, bot_username="b")
    st._codec = FakeTelegramLineStore([new, old])._codec  # new write key, old still readable
    assert st.get_line(line_id=rec.id, org_id=org, decrypt=True).bot_token == "1:" + "A" * 40
    st._codec = FakeTelegramLineStore([new])._codec
    with pytest.raises(TelegramLineStoreError):
        st.get_line(line_id=rec.id, org_id=org, decrypt=True)


class _Q:
    def __init__(self, db, table):
        self.db, self.t, self.f, self.op, self.payload = db, table, [], "select", None

    def select(self, *_):
        return self

    def insert(self, p):
        self.op, self.payload = "insert", p
        return self

    def eq(self, k, v):
        self.f.append((k, v))
        return self

    def neq(self, k, v):
        self.f.append((k, v, "neq"))
        return self

    def update(self, p):
        self.op, self.payload = "update", p
        return self

    def delete(self):
        self.op = "delete"
        return self

    def execute(self):
        rows = self.db.setdefault(self.t, [])
        if self.op == "insert":
            row = {**self.payload, "id": str(uuid4()), "created_at": "t"}
            rows.append(row)
            return type("R", (), {"data": [row]})

        def match(r):
            return all((str(r.get(f[0])) != str(f[1])) if len(f) == 3 else (str(r.get(f[0])) == str(f[1])) for f in self.f)

        hit = [r for r in rows if match(r)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
        if self.op == "delete":
            for r in hit:
                rows.remove(r)
        return type("R", (), {"data": hit})


class _Client:
    def __init__(self):
        self.db = {}

    def schema(self, s):
        return self

    def table(self, t):
        return _Q(self.db, t)


def test_supabase_line_store_org_filter_and_encryption_over_client():
    cl = _Client()
    st = SupabaseTelegramLineStore(cl, keys=[generate_key()], schema="s")
    org = uuid4()
    rec = st.create_line(org_id=org, created_by=uuid4(), label="L", bot_token="9:" + "B" * 40, bot_id=9, bot_username="b")
    assert "B" * 40 not in str(cl.db)
    assert st.get_line(line_id=rec.id, org_id=uuid4()) is None
    assert st.get_line(line_id=rec.id, org_id=org, decrypt=True).bot_token == "9:" + "B" * 40
    with pytest.raises(TelegramLineConflictError):
        st.create_line(org_id=org, created_by=uuid4(), label="L2", bot_token="9:" + "C" * 40, bot_id=9, bot_username="b")
    assert [r.id for r in st.list_lines(org_id=org)] == [rec.id]


# ---------------- events ----------------
def test_events_sink_persists_loud_and_validates_vocabulary():
    sink = make_telegram_line_event_sink(schema="s", use_fake=True)
    ev = TelegramLineEvent("telegram.post.sent", uuid4(), uuid4(), detail={"message_id": 3})
    sink.record(ev)
    assert sink.rows[0]["event"] == "telegram.post.sent" and sink.rows[0]["detail"] == {"message_id": 3}
    with pytest.raises(ValueError):
        TelegramLineEvent("not.an.event", uuid4())
    with pytest.raises(LineEventPersistenceError):
        FakeTelegramLineEventSink(fail_with=RuntimeError("db down")).record(ev)
    with pytest.raises(ValueError):
        make_telegram_line_event_sink(schema="s")


# ---------------- DDL ----------------
def test_ddl_every_table_declares_tier_and_grants_and_events_are_append_only():
    sql = telegram_tables_sql("newsletters")
    for t in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS newsletters.{t}" in sql
        assert f"COMMENT ON TABLE newsletters.{t} IS 'tier:" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "newsletters.telegram_lines IS 'tier:service'" in sql
    assert "newsletters.telegram_line_events IS 'tier:service'" in sql
    assert "newsletters.telegram_posts IS 'tier:org'" in sql
    assert "REVOKE ALL ON newsletters.telegram_lines FROM PUBLIC, anon, authenticated" in sql
    assert "GRANT SELECT ON newsletters.telegram_lines TO authenticated" not in sql
    assert "BEFORE UPDATE OR DELETE ON newsletters.telegram_line_events" in sql
    assert "message_id      BIGINT" in sql and "delete_deadline" in sql and "member_count" in sql
    assert sql == telegram_tables_sql("newsletters")  # deterministic
    with pytest.raises(ValueError):
        telegram_tables_sql("bad;schema")
