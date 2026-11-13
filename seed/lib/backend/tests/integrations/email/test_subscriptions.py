"""E-mail audience mechanism: tokens, suppression gate, lifecycle, router contract, Fake/Supabase parity, DDL."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.integrations.email import FakeEmailSender, OutgoingEmail, ResendConfig, ResendEmailSender
from noctusai_lib.integrations.email.subscriptions import (
    AudienceService, AudienceStoreNotConfigured, FakeAudienceStore, InvalidSubscriptionToken, RecipientSuppressed,
    SuppressionGuardedSender, SupabaseAudienceStore, email_audience_tables_sql, hash_email, issue_confirm_token,
    issue_unsubscribe_token, make_audience_store, normalize_email, one_click_headers, verify_confirm_token,
    verify_unsubscribe_token,
)
from noctusai_lib.integrations.email.subscriptions.router import make_subscription_router
from noctusai_lib.integrations.email.subscriptions.store import AudienceStore

SECRET = "s3cret-for-tests"


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


# ── hashing ──────────────────────────────────────────────────────────────
def test_hash_is_sha256_of_normalised_address():
    assert hash_email("  Foo@Bar.COM ") == hash_email("foo@bar.com")
    assert len(hash_email("a@b.co")) == 64 and "@" not in hash_email("a@b.co")
    with pytest.raises(Exception):
        normalize_email("not-an-email")


# ── tokens ───────────────────────────────────────────────────────────────
def test_confirm_token_roundtrip_expires_and_is_purpose_bound():
    clock = Clock()
    tok = issue_confirm_token(SECRET, "sid1", "h1", ttl_seconds=60, now=clock)
    assert verify_confirm_token(SECRET, tok, now=clock) == {"subscriber_id": "sid1", "email_hash": "h1"}
    clock.t += 61
    with pytest.raises(InvalidSubscriptionToken):
        verify_confirm_token(SECRET, tok, now=clock)
    with pytest.raises(InvalidSubscriptionToken):
        verify_unsubscribe_token(SECRET, issue_confirm_token(SECRET, "sid1", "h1"))


def test_unsubscribe_token_never_expires_and_tamper_fails():
    clock = Clock()
    tok = issue_unsubscribe_token(SECRET, "sid1", "h1", now=clock)
    clock.t += 10 * 365 * 24 * 3600
    assert verify_unsubscribe_token(SECRET, tok, now=clock)["subscriber_id"] == "sid1"
    body, mac = tok.split(".")
    for bad in (f"{body}x.{mac}", f"{body}.{mac[:-2]}ab", "garbage", ""):
        with pytest.raises(InvalidSubscriptionToken):
            verify_unsubscribe_token(SECRET, bad)
    with pytest.raises(InvalidSubscriptionToken):
        verify_unsubscribe_token("other-secret", tok)


def test_service_refuses_empty_secret():
    with pytest.raises(ValueError):
        AudienceService(FakeAudienceStore(), "")


# ── header pair ──────────────────────────────────────────────────────────
def test_one_click_header_pair_present_and_https_only():
    h = one_click_headers("https://news.example.com/u/abc", mailto="unsub@example.com")
    assert h["List-Unsubscribe"] == "<https://news.example.com/u/abc>, <mailto:unsub@example.com>"
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    with pytest.raises(ValueError):
        one_click_headers("http://news.example.com/u/abc")
    assert one_click_headers("http://localhost/u/abc", allow_http=True)["List-Unsubscribe-Post"]


def test_header_pair_reaches_resend_payload():
    svc = AudienceService(FakeAudienceStore(), SECRET)
    sub = svc.subscribe("a@b.com", source="test").subscriber
    headers = svc.unsubscribe_headers(sub, "https://n.example.com/api/subscriptions/unsubscribe")
    sender = ResendEmailSender(ResendConfig(api_key="k", from_email="n@x.com"))
    payload = sender._payload(OutgoingEmail(to=["a@b.com"], subject="s", html="<p>x</p>", headers=headers))
    assert payload["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert payload["headers"]["List-Unsubscribe"].startswith("<https://n.example.com/api/subscriptions/unsubscribe/")


# ── lifecycle ────────────────────────────────────────────────────────────
def _svc(store=None, clock=None):
    store = store or FakeAudienceStore()
    return AudienceService(store, SECRET, now=clock or Clock()), store


def test_double_opt_in_lifecycle_records_events_and_consent_without_ip():
    svc, store = _svc()
    res = svc.subscribe(" New@Site.com ", source="footer-form")
    assert res.created and res.subscriber.status == "pending" and res.subscriber.email == "new@site.com"
    assert res.subscriber.consent_source == "footer-form" and res.subscriber.consent_at is not None
    assert not hasattr(res.subscriber, "ip")
    assert svc.confirm(res.confirm_token) == "confirmed"
    assert svc.confirm(res.confirm_token) == "already"
    assert store.get_subscriber(res.subscriber.id).confirmed_at is not None
    assert [e.kind for e in store.list_events(res.subscriber.id)] == ["subscribed", "confirmed"]
    again = svc.subscribe("new@site.com", source="x")
    assert not again.created and again.confirm_token is None


def test_resubscribe_while_pending_reissues_token_without_new_event():
    svc, store = _svc()
    first = svc.subscribe("p@x.com", source="s")
    second = svc.subscribe("p@x.com", source="s")
    assert second.confirm_token and not second.created
    assert len(store.list_events(first.subscriber.id)) == 1


def test_expired_confirm_token_is_invalid():
    clock = Clock()
    svc, _ = _svc(clock=clock)
    res = svc.subscribe("e@x.com", source="s")
    clock.t += 8 * 24 * 3600
    with pytest.raises(InvalidSubscriptionToken):
        svc.confirm(res.confirm_token)


def test_unsubscribe_suppresses_by_hash_and_blocks_resubscribe():
    svc, store = _svc()
    sub = svc.subscribe("u@x.com", source="s").subscriber
    tok = issue_unsubscribe_token(SECRET, sub.id, sub.email_hash)
    assert svc.unsubscribe(tok) == "unsubscribed"
    assert svc.unsubscribe(tok) == "already"
    assert store.get_subscriber(sub.id).status == "unsubscribed"
    assert svc.is_suppressed("U@x.com")
    assert [e.kind for e in store.list_events(sub.id)] == ["subscribed", "unsubscribed"]
    with pytest.raises(RecipientSuppressed):
        svc.subscribe("u@x.com", source="s")
    with pytest.raises(InvalidSubscriptionToken):
        svc.confirm(issue_confirm_token(SECRET, sub.id, sub.email_hash))


def test_bounce_and_complaint_suppress_and_record_events():
    svc, store = _svc()
    a = svc.subscribe("b@x.com", source="s").subscriber
    c = svc.subscribe("c@x.com", source="s").subscriber
    svc.record_bounce("b@x.com")
    svc.record_complaint("c@x.com")
    svc.record_complaint("never-subscribed@x.com")  # still suppressed, no subscriber row
    assert store.get_subscriber(a.id).status == "bounced" and store.get_subscriber(c.id).status == "complained"
    assert [e.kind for e in store.list_events(a.id)][-1] == "bounced"
    assert [e.kind for e in store.list_events(c.id)][-1] == "complained"
    assert svc.is_suppressed("never-subscribed@x.com")


# ── suppression gate ─────────────────────────────────────────────────────
def test_send_to_suppressed_address_is_refused_with_typed_error_not_dropped():
    svc, store = _svc()
    store.add_suppression(hash_email("gone@x.com"), "unsubscribed")
    inner = FakeEmailSender()
    guarded = SuppressionGuardedSender(inner, store)
    with pytest.raises(RecipientSuppressed) as exc:
        asyncio.run(guarded.send(OutgoingEmail(to=["ok@x.com"], cc=["Gone@x.com"], subject="s", html="x")))
    assert exc.value.hashes == (hash_email("gone@x.com"),) and "gone@x.com" not in str(exc.value)
    assert inner.sent == [] if hasattr(inner, "sent") else True
    sent = asyncio.run(guarded.send(OutgoingEmail(to=["ok@x.com"], subject="s", html="x")))
    assert sent.message_id


# ── router contract ──────────────────────────────────────────────────────
def _client(svc):
    app = FastAPI()
    app.include_router(make_subscription_router(lambda: svc))
    return TestClient(app)


def test_router_tampered_or_wrong_purpose_token_is_strict_400():
    svc, _ = _svc()
    sub = svc.subscribe("r@x.com", source="s")
    client = _client(svc)
    unsub = issue_unsubscribe_token(SECRET, sub.subscriber.id, sub.subscriber.email_hash)
    for path in ("confirm", "unsubscribe"):
        for method in (client.get, client.post):
            assert method(f"/api/subscriptions/{path}/garbage").status_code == 400
    assert client.post(f"/api/subscriptions/confirm/{unsub}").status_code == 400  # wrong purpose
    assert client.post(f"/api/subscriptions/unsubscribe/{sub.confirm_token}").status_code == 400
    assert client.post(f"/api/subscriptions/unsubscribe/{unsub[:-3]}abc").status_code == 400


def test_router_confirm_and_one_click_unsubscribe_happy_path():
    svc, store = _svc()
    res = svc.subscribe("h@x.com", source="s")
    client = _client(svc)
    assert client.get(f"/api/subscriptions/confirm/{res.confirm_token}").json() == {"valid": True}
    assert client.post(f"/api/subscriptions/confirm/{res.confirm_token}").json() == {"ok": True, "already": False}
    unsub = issue_unsubscribe_token(SECRET, res.subscriber.id, res.subscriber.email_hash)
    r = client.post(f"/api/subscriptions/unsubscribe/{unsub}", data={"List-Unsubscribe": "One-Click"})
    assert r.status_code == 200 and r.json() == {"ok": True, "already": False}
    assert svc.is_suppressed("h@x.com")


def test_router_is_declared_service_tier():
    router = make_subscription_router(lambda: None)
    assert router.access_tier == "service"


# ── Fake <-> Supabase parity ─────────────────────────────────────────────
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, name):
        self.db, self.name, self.op, self.payload, self.filters, self.opts = db, name, "select", None, [], {}

    def select(self, *_):
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload, **opts):
        self.op, self.payload, self.opts = "upsert", payload, opts
        return self

    def eq(self, col, val):
        self.filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r, c=col, v=tuple(vals): r.get(c) in v)
        return self

    def limit(self, _):
        return self

    def order(self, _):
        return self

    def execute(self):
        import uuid
        from datetime import datetime, timezone
        rows = self.db.setdefault(self.name, [])
        if self.op == "insert":
            row = dict(self.payload)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("occurred_at", datetime.now(timezone.utc).isoformat())
            row.setdefault("consent_at", datetime.now(timezone.utc).isoformat())
            row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            rows.append(row)
            return _Resp([row])
        if self.op == "upsert":
            key = self.opts["on_conflict"]
            if not any(r[key] == self.payload[key] for r in rows):
                rows.append(dict(self.payload))
            return _Resp([])
        hit = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
        return _Resp([dict(r) for r in hit])


class _Client:
    def __init__(self):
        self.db: dict = {}

    def table(self, name):
        return _Query(self.db, name)


@pytest.fixture(params=["fake", "supabase"])
def store(request):
    return FakeAudienceStore() if request.param == "fake" else SupabaseAudienceStore(_Client())


def test_store_parity_conformance(store):
    assert isinstance(store, AudienceStore)
    sub = store.add_subscriber(email="a@x.com", email_hash="h1", status="pending", consent_source="src")
    assert store.get_subscriber(sub.id).email_hash == "h1" and store.find_by_hash("h1").id == sub.id
    assert store.find_by_hash("nope") is None and store.get_subscriber("nope") is None
    upd = store.update_subscriber(sub.id, status="confirmed")
    assert upd.status == "confirmed" and store.get_subscriber(sub.id).status == "confirmed"
    store.add_suppression("h1", "unsubscribed")
    store.add_suppression("h1", "bounced")  # idempotent
    assert store.suppressed_among(["h1", "h2"]) == {"h1"}
    store.append_event(sub.id, "subscribed", {"a": 1})
    store.append_event(sub.id, "confirmed")
    assert [e.kind for e in store.list_events(sub.id)] == ["subscribed", "confirmed"]


def test_full_lifecycle_runs_on_either_store(store):
    svc = AudienceService(store, SECRET)
    res = svc.subscribe("z@x.com", source="s")
    assert svc.confirm(res.confirm_token) == "confirmed"
    svc.unsubscribe(issue_unsubscribe_token(SECRET, res.subscriber.id, res.subscriber.email_hash))
    assert svc.is_suppressed("z@x.com")


def test_factory():
    assert isinstance(make_audience_store(use_fake=True), FakeAudienceStore)
    assert isinstance(make_audience_store(client=_Client()), SupabaseAudienceStore)
    with pytest.raises(AudienceStoreNotConfigured):
        make_audience_store()


# ── DDL ──────────────────────────────────────────────────────────────────
def test_ddl_declares_tiers_hashed_suppression_append_only_events_no_ip():
    sql = email_audience_tables_sql("newsletters")
    for table in ("subscribers", "suppression", "subscriber_events"):
        assert f"COMMENT ON TABLE newsletters.{table} IS 'tier:service'" in sql
    assert "email_hash TEXT PRIMARY KEY" in sql
    sup = sql.split("newsletters.suppression (")[1].split(");")[0]
    assert "email " not in sup and "ip" not in sup.lower().replace("description", "")
    assert "append_only" in sql and "REVOKE UPDATE, DELETE, TRUNCATE ON newsletters.subscriber_events" in sql
    assert "TO anon" not in sql and "TO authenticated" not in sql
    assert sql == email_audience_tables_sql("newsletters")
    with pytest.raises(ValueError):
        email_audience_tables_sql("bad schema;")
