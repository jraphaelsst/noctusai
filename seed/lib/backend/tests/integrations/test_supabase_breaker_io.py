"""Breaker IO: Redis store (via the seam, fakeredis) + owner email alerter (never silent when unconfigured)."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.email import FakeEmailSender
from noctusai_lib.integrations.supabase_breaker_io import (
    RedisBreakerStore,
    ResendBreakerAlerter,
    make_breaker_alerter,
    make_breaker_store,
)
from noctusai_lib.integrations.redis import make_fake_redis_client
from noctusai_lib.primitives.supabase_breaker import (
    BREAKER_FLEET_KEY,
    Breaker,
    BreakerAlertNotConfigured,
    InMemoryBreakerStore,
    RecordingAlerter,
)


def test_redis_store_roundtrip_has_no_ttl_and_mget_order():
    r = make_fake_redis_client()
    s = RedisBreakerStore(r)
    s.set("noctus:breaker:p:worker:a", '{"reason":"x"}')
    assert r.ttl("noctus:breaker:p:worker:a") == -1, "a trip must persist until a human re-arms"
    assert s.mget([BREAKER_FLEET_KEY, "noctus:breaker:p:worker:a"]) == [None, '{"reason":"x"}']
    s.delete("noctus:breaker:p:worker:a")
    assert s.get("noctus:breaker:p:worker:a") is None


def test_breaker_end_to_end_over_the_redis_store_and_fleet_key():
    r = make_fake_redis_client()
    b = Breaker(slug="p", store=RedisBreakerStore(r), alerter=RecordingAlerter(), sync_io=True, fleet_ttl_s=0.0)
    b.trip("worker:a", reason="runaway")
    assert r.exists("noctus:breaker:p:worker:a")
    r.set(BREAKER_FLEET_KEY, '{"reason":"402","by":"watcher"}')
    assert b.check_sync("scheduler:x", force=True)["scope"] == "fleet"


def test_alerter_names_exactly_what_is_missing():
    with pytest.raises(BreakerAlertNotConfigured) as e:
        ResendBreakerAlerter({}).send("s", "b")
    assert "RESEND_API_KEY" in str(e.value) and "NOCTUS_BREAKER_ALERT_EMAIL" in str(e.value)
    with pytest.raises(BreakerAlertNotConfigured) as e:
        ResendBreakerAlerter({"RESEND_API_KEY": "k"}).send("s", "b")
    assert "RESEND_API_KEY" not in str(e.value) and "ALERT_EMAIL" in str(e.value)


def test_alerter_sends_through_the_seed_email_seam_with_watchdog_recipient_fallback():
    sent = FakeEmailSender()
    a = ResendBreakerAlerter({"RESEND_API_KEY": "k", "WATCHDOG_ALERT_EMAIL": "owner@example.com"},
                             sender_factory=lambda cfg: sent)
    a.send("subject", "body")
    assert sent.sent[0].to == ["owner@example.com"] and sent.sent[0].subject == "subject"


def test_factories_use_fakes_when_asked_and_log_when_no_redis(monkeypatch, caplog):
    assert isinstance(make_breaker_store(use_fake=True), InMemoryBreakerStore)
    assert isinstance(make_breaker_alerter(use_fake=True), RecordingAlerter)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with caplog.at_level("ERROR"):
        assert isinstance(make_breaker_store(None), InMemoryBreakerStore)
    assert "no REDIS_URL" in caplog.text


# --- Redis ACL compatibility: a product writes ONLY under noctus:breaker:<slug>:* and reads only the fleet key -----


class _SpyRedis:
    """Records every key a command touches, then delegates to fakeredis."""

    def __init__(self):
        self._r = make_fake_redis_client()
        self.written: set[str] = set()
        self.read: set[str] = set()

    def __getattr__(self, name):
        fn = getattr(self._r, name)

        def call(*a, **kw):
            keys = [x for x in a if isinstance(x, str) and x.startswith("noctus:")] + \
                   ([k for x in a if isinstance(x, list) for k in x])
            (self.written if name in ("set", "delete", "sadd", "srem", "rpush", "ltrim") else self.read).update(keys)
            return fn(*a, **kw)

        return call

    def pipeline(self):  # the audit cap path
        outer = self
        pipe = self._r.pipeline()

        class P:
            def rpush(self, k, v):
                outer.written.add(k)
                pipe.rpush(k, v)
                return self

            def ltrim(self, k, a, b):
                outer.written.add(k)
                pipe.ltrim(k, a, b)
                return self

            def execute(self):
                return pipe.execute()

        return P()


def test_product_writes_only_inside_its_slug_namespace_and_reads_only_fleet_plus_own_keys():
    spy = _SpyRedis()
    b = Breaker(slug="social-wiring", store=RedisBreakerStore(spy), alerter=RecordingAlerter(), sync_io=True,
                fleet_ttl_s=0.0)
    b.trip("worker:a", reason="runaway", rate=3, window=300)
    b.check_sync("worker:a", force=True)
    b.rearm("worker:a", by="ana", reason="fixed")
    assert spy.written, "nothing was written?"
    assert all(k.startswith("noctus:breaker:social-wiring:") for k in spy.written), spy.written
    assert all(k == BREAKER_FLEET_KEY or k.startswith("noctus:breaker:social-wiring:") for k in spy.read), spy.read
    assert "noctus:breaker:audit" not in spy.written, "the global audit list is ops-only"


def test_per_source_keys_are_indexed_and_deindexed_never_scanned():
    r = make_fake_redis_client()
    s = RedisBreakerStore(r)
    s.set("noctus:breaker:p:worker:a", "{}")
    s.set(BREAKER_FLEET_KEY, "{}")
    assert r.smembers("noctus:breaker:p:index") == {"noctus:breaker:p:worker:a"}
    assert not r.exists("noctus:breaker:index"), "fleet is not indexed"
    s.delete("noctus:breaker:p:worker:a")
    assert r.smembers("noctus:breaker:p:index") == set()


def test_operator_set_key_is_indexed_when_the_product_first_observes_it():
    r = make_fake_redis_client()
    b = Breaker(slug="p", store=RedisBreakerStore(r), alerter=RecordingAlerter(), sync_io=True, fleet_ttl_s=0.0)
    r.set("noctus:breaker:p:worker:z", '{"reason":"manual","by":"manual:ana"}')  # ops has no SADD
    assert b.check_sync("worker:z", force=True) is not None
    assert r.smembers("noctus:breaker:p:index") == {"noctus:breaker:p:worker:z"}


def test_a_product_cannot_rearm_the_fleet_key():
    r = make_fake_redis_client()
    r.set(BREAKER_FLEET_KEY, "{}")
    b = Breaker(slug="p", store=RedisBreakerStore(r), alerter=RecordingAlerter(), sync_io=True)
    with pytest.raises(ValueError):
        b.rearm("fleet", by="ana", reason="x")
    assert r.exists(BREAKER_FLEET_KEY)


def test_rearm_marker_and_audit_keys_are_never_indexed_as_held_sources():
    for k in ("noctus:breaker:p:rearm:worker:a", "noctus:breaker:p:audit", "noctus:breaker:p:index", BREAKER_FLEET_KEY):
        assert RedisBreakerStore.index_key(k) is None, k
    assert RedisBreakerStore.index_key("noctus:breaker:p:worker:a") == "noctus:breaker:p:index"
